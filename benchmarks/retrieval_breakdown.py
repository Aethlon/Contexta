"""Where does the ~1.2s of a real retrieval go? Vary one knob at a time."""

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


def mint_key() -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    sql = (
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'breakdown', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{USER}', ARRAY['read','write'], now());"
    )
    subprocess.run(["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
                    "-d", "contexta", "-c", sql], capture_output=True, text=True, check=False)
    return token


def run(client, headers, **overrides):
    body = {"user_id": USER, "organization_id": ORG,
            "query_text": "where does the user live and what do they prefer",
            "limit": 10}
    body.update(overrides)
    samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = client.post(f"{API}/v1/retrieve", json=body, headers=headers)
        samples.append((time.perf_counter() - t0) * 1000)
        if r.status_code >= 300:
            print("   http", r.status_code, r.text[:160])
            return None
    return samples


def show(label, samples):
    if samples is None:
        print(f"  {label:38s} FAILED")
        return
    print(f"  {label:38s} p50={statistics.median(samples):7.1f} ms  min={min(samples):7.1f} ms")


def main() -> int:
    key = mint_key()
    headers = {"x-api-key": key}
    with httpx.Client(timeout=300.0) as client:
        print("=== retrieval cost breakdown (5 runs each) ===")
        show("default (depth=1, rerank on)", run(client, headers))
        show("graph_depth=0", run(client, headers, graph_depth=0))
        show("rerank=False", run(client, headers, rerank=False))
        show("graph_depth=0 + rerank=False", run(client, headers, graph_depth=0, rerank=False))
        show("limit=1", run(client, headers, limit=1))
        show("short query", run(client, headers, query_text="preferences"))

        print("\n=== model server isolated ===")
        t0 = time.perf_counter()
        client.post("http://localhost:8001/v1/embeddings",
                    json={"input": ["where does the user live and what do they prefer"],
                          "model": "Qwen/Qwen3-Embedding-0.6B"})
        print(f"  embed x1                                  {(time.perf_counter()-t0)*1000:7.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
