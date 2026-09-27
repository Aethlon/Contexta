"""Retrieval diagnostic against a tenant that actually has memories.

Reports whether each retrieval layer returns candidates, and the latency of each.
"""

import hashlib
import secrets
import statistics
import subprocess
import sys
import time
import uuid

import httpx

API = "http://localhost:8000"
ORG = "00000000-0000-0000-0000-000000000001"
USER = "4befdce9-64e1-525a-bb9a-d5707dbbe94e"


def mint_key() -> tuple[str, str]:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    actor = str(uuid.uuid4())
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'retrieval-diag', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{actor}', ARRAY['read','write'], now());"
    )
    subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return token, actor


def bench(fn, n=5):
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        res = fn()
        out.append(((time.perf_counter() - t0) * 1000, res))
    times = [t for t, _ in out]
    return statistics.median(times), min(times), out[-1][1]


def main():
    token, _actor = mint_key()
    headers = {"x-api-key": token}

    with httpx.Client(timeout=300.0) as client:
        for rerank in (True, False):
            def call(r=rerank):
                resp = client.post(
                    f"{API}/v1/retrieve",
                    json={"user_id": USER, "organization_id": ORG,
                          "query_text": "where does the user live and what do they prefer",
                          "limit": 10, "rerank": r},
                    headers=headers,
                )
                return (resp.status_code, resp.json() if resp.status_code < 300
                        else resp.text[:300])

            med, best, last = bench(call, n=5)
            print(f"\n=== retrieve (rerank={rerank}) p50={med:.0f}ms min={best:.0f}ms ===")
            status, data = last
            print("status:", status)
            if isinstance(data, str):
                print("body:", data)
                continue
            items = data.get("memories") or data.get("results") or []
            print("hits:", len(items) if isinstance(items, list) else "n/a")
            print("top-level keys:", sorted(data.keys())[:14])
            if isinstance(items, list) and items:
                for it in items[:3]:
                    print("  -", str(it)[:200])
                print("  fields:", sorted(items[0].keys())[:16])
            elif isinstance(items, list):
                print("  (no candidates)")

        # Diagnose the layer counts directly in SQL.
        print("\n=== layer diagnostics (SQL) ===")
        for label, sql in [
            ("dense (embedding IS NOT NULL)",
             f"SELECT count(*) FROM memory_record WHERE organization_id='{ORG}' "
             f"AND user_id='{USER}' AND embedding IS NOT NULL AND memory_state='active';"),
            ("dense + profile filter",
             f"SELECT count(*) FROM memory_record WHERE organization_id='{ORG}' "
             f"AND user_id='{USER}' AND embedding_profile='offline-qwen3-1024';"),
            ("fulltext candidates",
             f"SELECT count(*) FROM memory_record WHERE organization_id='{ORG}' "
             f"AND user_id='{USER}' AND search_vector @@ plainto_tsquery('english','user');"),
        ]:
            out = subprocess.run(
                ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
                 "-d", "contexta", "-t", "-A", "-c", sql],
                capture_output=True, text=True, check=False,
            )
            print(f"  {label:34s} -> {out.stdout.strip()[:80]}")


if __name__ == "__main__":
    sys.exit(main())
