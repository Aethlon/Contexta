"""Mint a dev API key and write CONTEXTA_MCP_API_KEY into the gitignored .env."""

import hashlib
import pathlib
import secrets
import subprocess
import sys
import uuid

ORG = "96d29395-6d90-4ba2-9eed-6a851e0290c1"
ENV = pathlib.Path(".env")


def main() -> int:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    actor = str(uuid.uuid4())
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'mcp-local', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{actor}', ARRAY['read','write'], now());"
    )
    out = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        print("insert failed:", out.stderr[:300])
        return 1

    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    lines = [
        line for line in text.splitlines()
        if not line.startswith(("CONTEXTA_MCP_API_KEY", "CONTEXTA_MCP_ALLOW_ANONYMOUS"))
    ]
    lines += [
        "# MCP authenticates every caller with a Contexta API key. This is a local",
        "# development key scoped to the default org; rotate it for any shared host.",
        f"CONTEXTA_MCP_API_KEY={token}",
        "CONTEXTA_MCP_ALLOW_ANONYMOUS=false",
    ]
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote CONTEXTA_MCP_API_KEY to .env (gitignored)")
    print(f"org={ORG} actor={actor}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
