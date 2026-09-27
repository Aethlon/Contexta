"""Exercise the graph/traverse endpoints, which previously raised NameError."""

import hashlib
import secrets
import subprocess
import sys
import uuid

import httpx

BASE = "http://localhost:8000"
ORG = "00000000-0000-0000-0000-000000000001"
USER = "4befdce9-64e1-525a-bb9a-d5707dbbe94e"


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def mint() -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    psql(
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'graph', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{USER}', ARRAY['read','write'], now());"
    )
    return token


def main() -> int:
    key = mint()
    entity = psql("SELECT name FROM entity LIMIT 1;")
    print(f"testing with entity: {entity!r}\n")
    headers = {"x-api-key": key}
    failures = 0
    with httpx.Client(timeout=120.0) as client:
        for path in (
            "/v1/graph/traverse",
            "/v1/entities/traverse",
            "/v1/graph/graph/traverse",
        ):
            for hops in (1, 2):
                r = client.get(f"{BASE}{path}", headers=headers,
                               params={"source": entity, "hops": hops})
                ok = r.status_code == 200
                if not ok:
                    failures += 1
                detail = ""
                if ok:
                    body = r.json()
                    detail = f"keys={sorted(body)[:6]}"
                else:
                    detail = r.text[:140]
                print(f"{'PASS' if ok else 'FAIL'} GET {path} hops={hops} "
                      f"-> {r.status_code} {detail}")
    print(f"\n{'all traverse endpoints OK' if not failures else f'{failures} failures'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
