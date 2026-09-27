"""Reproduce the /v1/kernel/recall failure and surface the real exception."""

import hashlib
import json
import secrets
import subprocess
import sys
import uuid

import httpx

ORG = "00000000-0000-0000-0000-000000000001"
ACTOR = "4befdce9-64e1-525a-bb9a-d5707dbbe94e"


def mint() -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'kb', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{ACTOR}', ARRAY['read','write'], now());"
    )
    subprocess.run(["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
                    "-d", "contexta", "-c", sql], capture_output=True, text=True, check=False)
    return token


def main() -> int:
    token = mint()
    with httpx.Client(timeout=180.0) as client:
        for label, payload in [
            ("recall", {"scope": {"tenant_id": ORG, "user_id": ACTOR},
                        "query": "preferences"}),
            ("recall+limit", {"scope": {"tenant_id": ORG, "user_id": ACTOR},
                              "query": "preferences", "limit": 5}),
            ("recall+mem_user", {"scope": {"tenant_id": ORG, "user_id": ACTOR,
                                          "memory_user_id": ACTOR},
                                 "query": "preferences"}),
        ]:
            r = client.post("http://localhost:8000/v1/kernel/recall", json=payload,
                            headers={"x-api-key": token})
            print(f"\n--- {label}: {r.status_code}")
            try:
                d = r.json()
            except Exception:
                print(r.text[:300])
                continue
            if isinstance(d, dict) and d.get("error"):
                print("  error:", json.dumps(d["error"], indent=2)[:700])
            else:
                print("  keys:", sorted(d)[:12])
                print("  total:", d.get("total"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
