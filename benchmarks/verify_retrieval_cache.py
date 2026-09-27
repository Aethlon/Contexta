"""Verify the retrieval caches: Python query-embedding cache and Go edge cache.

Measures cold vs warm latency for a repeated query and reports the
`X-Contexta-Cache` header so the edge cache hit/miss is observable.
"""

import hashlib
import secrets
import statistics
import subprocess
import sys
import time
import uuid

import httpx

GATEWAY = "https://localhost:8443"
API = "http://localhost:8000"
ORG = "00000000-0000-0000-0000-000000000001"
USER = "4befdce9-64e1-525a-bb9a-d5707dbbe94e"
QUERY = "where does the user live and what do they prefer"


def mint_key() -> str:
    """Create a key in Postgres *and* publish it to Redis.

    The Go gateway verifies API keys from Redis only (it has no Postgres
    fallback), so a row inserted straight into the database is invisible to it.
    """
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    key_id = str(uuid.uuid4())
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{key_id}', 'cache-verify', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{USER}', ARRAY['read','write'], now());"
    )
    subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    redis_key = f"apikey:{token_hash}"
    subprocess.run(
        ["docker", "exec", "memento-redis-1", "redis-cli", "-n", "0", "DEL", redis_key],
        capture_output=True, text=True, check=False,
    )
    for field, value in (
        ("key_id", key_id),
        ("tenant_id", ORG),
        ("actor_id", USER),
        ("scopes", "read write"),
        ("tier", "standard"),
    ):
        subprocess.run(
            ["docker", "exec", "memento-redis-1", "redis-cli", "-n", "0",
             "HSET", redis_key, field, value],
            capture_output=True, text=True, check=False,
        )
    return token


def timed(client, url, headers, body, n):
    out = []
    headers_seen = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = client.post(url, json=body, headers=headers)
        out.append((time.perf_counter() - t0) * 1000)
        headers_seen.append(r.headers.get("x-contexta-cache", "-"))
    return out, headers_seen


def show(label, samples):
    print(f"  {label:34s} p50={statistics.median(samples):7.1f} ms  "
          f"min={min(samples):7.1f} ms  max={max(samples):7.1f} ms")


def main() -> int:
    key = mint_key()
    headers = {"x-api-key": key}
    body = {"user_id": USER, "organization_id": ORG, "query_text": QUERY,
            "limit": 10, "rerank": True}

    print("=== direct to Python API :8000 (query-embedding cache) ===")
    with httpx.Client(timeout=300.0) as client:
        cold, _ = timed(client, f"{API}/v1/retrieve", headers, body, 3)
        show("first calls (cold)", cold)
        warm, _ = timed(client, f"{API}/v1/retrieve", headers, body, 8)
        show("repeat calls (warm)", warm)

    print("\n=== through Go gateway :8443 (edge response cache) ===")
    with httpx.Client(timeout=300.0, verify=False) as client:
        samples, cache_headers = timed(client, f"{GATEWAY}/v1/retrieve", headers, body, 10)
        show("all calls", samples)
        print("  X-Contexta-Cache sequence:", ",".join(cache_headers))
        hits = sum(1 for h in cache_headers if h in {"hit", "coalesced"})
        print(f"  cache hits: {hits}/{len(cache_headers)}")

    print("\n=== burst of identical concurrent queries (single-flight) ===")
    import concurrent.futures

    with httpx.Client(timeout=300.0, verify=False) as client:
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futures = [
                pool.submit(client.post, f"{GATEWAY}/v1/retrieve", json=body, headers=headers)
                for _ in range(10)
            ]
            results = [f.result() for f in futures]
        burst = (time.perf_counter() - t0) * 1000
        statuses = {r.status_code for r in results}
        print(f"  10 concurrent identical queries: {burst:.0f} ms, statuses={statuses}")
        print(f"  per-request avg: {burst / 10:.0f} ms")

    return 0


if __name__ == "__main__":
    sys.exit(main())
