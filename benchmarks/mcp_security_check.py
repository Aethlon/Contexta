"""MCP security checks that need a live database, run inside the stack.

Run it in-container, where CONTEXTA_DATABASE_URL and the model server both resolve:

    docker cp benchmarks/mcp_security_check.py memento-worker-1:/tmp/ && \\
      docker compose exec -T worker python /tmp/mcp_security_check.py

Running it on the host fails on a connection error, not on a security assertion,
because postgres and the model server are not published to the host.
"""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.environ.get("CONTEXTA_APP_ROOT", "/app"))

from contexta.mcp.security import McpSecurityError, resolve_tenant  # noqa: E402
from contexta.mcp.server import create_mcp_server  # noqa: E402
from contexta.mcp.service import ContextaMCPService  # noqa: E402

# The probe must mint its own tenant: a hard-coded UUID belongs to whatever
# database happened to exist when this was written, and against a fresh volume it
# is simply an organization with no rows.
ORG = uuid.UUID(
    os.environ.get("MCP_CHECK_ORG_ID", "96d29395-6d90-4ba2-9eed-6a851e0290c1")
)
PROBE_USER = os.environ.get("MCP_CHECK_USER_ID", str(uuid.uuid4()))
MODEL_SERVER = os.environ.get("MCP_CHECK_MODEL_SERVER", "http://model-server:8001")
results = []


def check(name, condition, detail=""):
    results.append((name, bool(condition), detail))
    print(f"{'PASS' if condition else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


# 1. tenant comes from the constructor, not the hard-coded default
service = ContextaMCPService(organization_id=ORG)
check("service uses injected tenant", service.org_id == ORG, str(service.org_id))

# 2. server refuses to bootstrap with a bad key
os.environ["CONTEXTA_MCP_API_KEY"] = "mk_live_not_a_real_key_at_all"
try:
    create_mcp_server()
    check("server rejects unknown key", False, "started anyway")
except McpSecurityError as exc:
    check("server rejects unknown key", True, str(exc)[:50])
except Exception as exc:
    check("server rejects unknown key", False, f"{type(exc).__name__}: {exc}"[:80])

# 3. server refuses to bootstrap with no key
os.environ.pop("CONTEXTA_MCP_API_KEY", None)
os.environ.pop("CONTEXTA_MCP_ALLOW_ANONYMOUS", None)
try:
    create_mcp_server()
    check("server requires auth", False, "started anyway")
except McpSecurityError as exc:
    check("server requires auth", True, str(exc)[:50])
except Exception as exc:
    check("server requires auth", False, f"{type(exc).__name__}: {exc}"[:80])


# 4. remember() redacts PII before anything is stored
async def exercise_remember():
    # Default model_server_url is localhost:8001, which is the worker container's
    # own loopback and refuses the connection. Point it at the model-server service.
    svc = ContextaMCPService(model_server_url=MODEL_SERVER, organization_id=ORG)
    captured = {}

    async def fake_embed(_text):
        return [0.0] * 1024

    svc._embedder.embed = fake_embed

    real_add = None

    class Wrapped:
        def __init__(self, inner):
            self.inner = inner

        def __getattr__(self, item):
            return getattr(self.inner, item)

    try:
        result = await svc.remember(
            "My email is dana.whitfield@northwind-logistics.com and my card is 4111 1111 1111 1111.",
            # user_id is a UUID column; a bare string fails the insert.
            user_id=PROBE_USER,
            memory_type="fact",
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return result, ""


outcome, detail = asyncio.run(exercise_remember())
if outcome is None:
    check("remember() redacts PII", False, detail[:110])
else:
    rendered = str(outcome)
    leaked_email = "dana.whitfield@northwind-logistics.com" in rendered
    leaked_card = "4111 1111 1111 1111" in rendered
    check("remember() redacts PII", not (leaked_email or leaked_card),
          f"email_leaked={leaked_email} card_leaked={leaked_card}")

# 5. what actually landed in the database for that probe user.
#
# Content is encrypted at rest, so the obvious `content LIKE '%secret%'` probe
# matches nothing and the loop below never runs — the check silently passes
# without asserting anything. Decrypt the probe row instead, which is also the
# only way to see what the redaction gate actually produced.
print("\n--- row written by the MCP probe, decrypted ---")
try:
    from sqlalchemy import text

    from contexta.core.crypto.vault import decrypt_content
    from contexta.db import AsyncSessionFactory

    async def read_probe():
        async with AsyncSessionFactory() as s:
            r = await s.execute(
                text(
                    "SELECT content FROM memory_record "
                    "WHERE organization_id = :org AND user_id = :user "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"org": str(ORG), "user": str(PROBE_USER)},
            )
            return r.scalar()

    token = asyncio.run(read_probe())
    if not token:
        check("probe row was persisted", False, "no row for the probe user")
    else:
        check("probe row was persisted", True, f"{len(token)} chars at rest")
        plain = decrypt_content(token, str(ORG)) or ""
        print("   plaintext: %s" % plain)
        check(
            "persisted plaintext is redacted",
            "[REDACTED" in plain
            and "dana.whitfield@northwind-logistics.com" not in plain
            and "4111 1111 1111 1111" not in plain,
            plain[:80],
        )
except Exception as exc:
    check("persisted plaintext is redacted", False, f"{type(exc).__name__}: {exc}")

failed = [name for name, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("FAILED:", failed)
sys.exit(1 if failed else 0)
