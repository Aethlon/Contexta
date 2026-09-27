"""MCP security checks that need a live database, run inside the stack."""

import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app")

from contexta.mcp.security import McpSecurityError, resolve_tenant  # noqa: E402
from contexta.mcp.server import create_mcp_server  # noqa: E402
from contexta.mcp.service import ContextaMCPService  # noqa: E402

ORG = uuid.UUID("96d29395-6d90-4ba2-9eed-6a851e0290c1")
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
    svc = ContextaMCPService(organization_id=ORG)
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
            user_id="mcp-probe-user",
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

# 5. what actually landed in the database for that probe user
print("\n--- rows written by the MCP probe ---")
try:
    from sqlalchemy import text

    from contexta.db import AsyncSessionFactory

    async def count():
        async with AsyncSessionFactory() as s:
            r = await s.execute(
                text(
                    "SELECT organization_id, count(*), bool_or(content LIKE '%northwind-logistics%') "
                    "FROM memory_record WHERE content LIKE '%northwind-logistics%' "
                    "OR content LIKE '%4111 1111%' GROUP BY 1"
                )
            )
            return r.fetchall()

    for row in asyncio.run(count()):
        print("   org=%s rows=%s leaked=%s" % tuple(row))
        check("no raw PII persisted", not row[2], "content contains the raw secret")
except Exception as exc:
    print(f"   (db probe skipped: {type(exc).__name__}: {exc})")

failed = [name for name, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("FAILED:", failed)
sys.exit(1 if failed else 0)
