"""Mint a dev API key and run the full ingest -> memory -> recall round-trip.

The API key's actor_id is used as the user_id, because the auth middleware
rejects a request whose user_id disagrees with the authenticated identity.
"""

import hashlib
import json
import secrets
import subprocess
import sys
import time
import uuid

import httpx

ORG = "96d29395-6d90-4ba2-9eed-6a851e0290c1"
BASE = "http://localhost:8000"
WAIT_SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 240


def mint_key() -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    actor = str(uuid.uuid4())
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'e2e-smoke', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{actor}', ARRAY['read','write'], now());"
    )
    result = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        print("key mint failed:", result.stderr[:400])
        sys.exit(1)
    return token, actor


def main() -> int:
    token, actor = mint_key()
    headers = {"x-api-key": token, "X-User-Id": actor}
    content = (
        "Hi, I'm Dana Whitfield and I own the billing integration. "
        "I prefer dark mode in every dashboard and I am based in Seattle. "
        "My email is dana.whitfield@northwind-logistics.com and my card is 4111 1111 1111 1111."
    )
    body = {
        "user_id": actor,
        "organization_id": ORG,
        "session_id": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": content}],
    }

    with httpx.Client(timeout=90.0) as client:
        r = client.post(f"{BASE}/v1/observations", json=body, headers=headers)
        print(f"POST /v1/observations -> {r.status_code}")
        if r.status_code >= 300:
            print(r.text[:600])
            return 1
        job_id = r.json()["job_id"]
        print(f"job_id={job_id}")

        deadline = time.time() + WAIT_SECONDS
        final = "timeout"
        while time.time() < deadline:
            time.sleep(6)
            s = client.get(f"{BASE}/v1/observations/{job_id}/status", headers=headers)
            if s.status_code >= 300:
                print("  status http", s.status_code, s.text[:200])
                break
            final = s.json().get("status", "?")
            if final in {"completed", "failed", "dead_letter"}:
                break
        print(f"final status: {final}")

        q = client.post(
            f"{BASE}/v1/retrieve",
            json={
                "user_id": actor,
                "organization_id": ORG,
                "query_text": "what does Dana prefer and where is she based",
                "limit": 5,
            },
            headers=headers,
        )
        print(f"\nPOST /v1/retrieve -> {q.status_code}")
        if q.status_code >= 300:
            print(q.text[:600])
            return 1
        data = q.json()
        items = data.get("memories") or data.get("results") or []
        print(f"hits: {len(items) if isinstance(items, list) else 'n/a'}")
        for item in (items if isinstance(items, list) else [])[:5]:
            print("  -", json.dumps(item)[:220])
        print("\nPASS" if final == "completed" else f"\nFINAL={final}")
    return 0 if final == "completed" else 2


if __name__ == "__main__":
    sys.exit(main())
