"""Mint a dev API key directly in Postgres, matching ApiKeyRepository.create_key."""

import hashlib
import secrets
import subprocess
import sys
import uuid

ORG = "96d29395-6d90-4ba2-9eed-6a851e0290c1"
ACTOR = str(uuid.uuid4())

token = f"mk_live_{secrets.token_urlsafe(32)}"
token_hash = hashlib.sha256(token.encode()).hexdigest()
prefix = token[:16]

sql = (
    "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
    "scopes, created_at) VALUES "
    f"('{uuid.uuid4()}', 'e2e-smoke', '{prefix}', '{token_hash}', '{ORG}', '{ACTOR}', "
    "ARRAY['read','write'], now());"
)

result = subprocess.run(
    ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres", "-d", "contexta", "-c", sql],
    capture_output=True,
    text=True,
    check=False,
)
if result.returncode != 0:
    print("FAILED:", result.stderr[:500])
    sys.exit(1)

print("TOKEN=" + token)
print("ACTOR=" + ACTOR)
print("ORG=" + ORG)
