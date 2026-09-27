"""End-to-end: does an observation now become a real extracted memory?

Posts a conversation with known extractable facts, waits for the worker, then reads
back what was actually stored. This is the check that matters after switching
extraction to the fine-tuned model.
"""

import hashlib
import json
import secrets
import subprocess
import sys
import time
import uuid

import httpx

BASE = "http://localhost:8000"
ORG = "00000000-0000-0000-0000-000000000001"

CONVERSATION = (
    "user: Hi, I'm Dana Whitfield and I own the billing integration at Northwind. "
    "I prefer dark mode in every dashboard and I always deploy on Fridays. "
    "My rule is that no merge ships without two approvals."
)


def psql(sql: str) -> str:
    out = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def mint(actor: str) -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    psql(
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'extract-e2e', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{actor}', ARRAY['read','write'], now());"
    )
    return token


def main() -> int:
    actor = str(uuid.uuid4())
    key = mint(actor)
    headers = {"x-api-key": key}
    body = {
        "user_id": actor,
        "organization_id": ORG,
        "session_id": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": CONVERSATION}],
    }

    with httpx.Client(timeout=300.0) as client:
        r = client.post(f"{BASE}/v1/observations", json=body, headers=headers)
        print(f"POST /v1/observations -> {r.status_code}")
        if r.status_code >= 300:
            print(r.text[:400])
            return 1
        job_id = r.json()["job_id"]

        final = "timeout"
        deadline = time.time() + 300
        while time.time() < deadline:
            time.sleep(6)
            s = client.get(f"{BASE}/v1/observations/{job_id}/status", headers=headers)
            if s.status_code >= 300:
                print("  status http", s.status_code)
                break
            final = s.json().get("status", "?")
            if final in {"completed", "failed", "dead_letter"}:
                break
        print(f"final status: {final}\n")

        count = psql(
            f"SELECT count(*) FROM memory_record WHERE organization_id='{ORG}' "
            f"AND user_id='{actor}';"
        )
        print(f"memories stored for this user: {count}")

        rows = psql(
            f"SELECT memory_type || ' | ' || left(title,70) || ' | ' || left(content,90) "
            f"FROM memory_record WHERE organization_id='{ORG}' AND user_id='{actor}' "
            f"ORDER BY created_at;"
        )
        print("stored memories:")
        for line in (rows or "").splitlines():
            print("  -", line)

        structured = psql(
            f"SELECT count(*) FROM memory_record WHERE organization_id='{ORG}' "
            f"AND user_id='{actor}' AND structured_data IS NOT NULL;"
        )
        print(f"\nmemories with structured_data (S-P-O): {structured}")

    ok = int(count or 0) > 0
    print("\nRESULT:", "PASS - memories extracted" if ok else "FAIL - no memories stored")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
