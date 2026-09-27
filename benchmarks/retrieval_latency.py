"""Latency breakdown for the retrieval path: embed / rerank / end-to-end retrieve."""

import statistics
import subprocess
import sys
import time
import uuid

import httpx

MODEL = "http://localhost:8001"
API = "http://localhost:8000"
ORG = "96d29395-6d90-4ba2-9eed-6a851e0290c1"
N = 5


def timeit(fn, n=N):
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return {
        "mean": statistics.mean(samples),
        "p50": statistics.median(samples),
        "min": min(samples),
        "max": max(samples),
    }


def fmt(label, stats):
    print(f"  {label:38s} mean={stats['mean']:9.1f} ms   p50={stats['p50']:9.1f} ms"
          f"   min={stats['min']:9.1f} ms")


def main():
    with httpx.Client(timeout=300.0) as client:
        print("=== model server (:8001) ===")

        def embed_one():
            client.post(f"{MODEL}/v1/embeddings",
                        json={"input": ["what does the user prefer"],
                              "model": "Qwen/Qwen3-Embedding-0.6B"})

        def embed_batch():
            client.post(f"{MODEL}/v1/embeddings",
                        json={"input": [f"document number {i} about billing"
                                        for i in range(45)],
                              "model": "Qwen/Qwen3-Embedding-0.6B"})

        fmt("embed x1", timeit(embed_one))
        fmt("embed x45 (RRF pool size)", timeit(embed_batch))

        docs = [{"id": str(i), "text": f"User prefers dark mode in dashboard {i}"}
                for i in range(45)]

        def rerank_45():
            client.post(f"{MODEL}/v1/rerank",
                        json={"model": "Qwen/Qwen3-Reranker-0.6B",
                              "query": "what does the user prefer",
                              "documents": [d["text"] for d in docs]})

        try:
            fmt("rerank x45", timeit(rerank_45, n=3))
        except Exception as exc:  # noqa: BLE001
            print(f"  rerank failed: {type(exc).__name__}: {str(exc)[:200]}")

        print("\n=== end-to-end /v1/retrieve ===")
        token = subprocess.run(
            [sys.executable, "benchmarks/mint_dev_key.py"],
            capture_output=True, text=True, check=False,
        ).stdout
        key = next(l.split("=", 1)[1] for l in token.splitlines() if l.startswith("TOKEN="))
        actor = next(l.split("=", 1)[1] for l in token.splitlines() if l.startswith("ACTOR="))
        headers = {"x-api-key": key, "X-User-Id": actor}

        def retrieve():
            r = client.post(
                f"{API}/v1/retrieve",
                json={"user_id": actor, "organization_id": ORG,
                      "query_text": "what does the user prefer",
                      "limit": 10, "rerank": True},
                headers=headers,
            )
            if r.status_code >= 300:
                raise RuntimeError(f"http {r.status_code}: {r.text[:200]}")

        try:
            fmt("retrieve (rerank=true)", timeit(retrieve, n=5))
        except Exception as exc:  # noqa: BLE001
            print(f"  retrieve failed: {type(exc).__name__}: {str(exc)[:300]}")

        def retrieve_norerank():
            client.post(
                f"{API}/v1/retrieve",
                json={"user_id": actor, "organization_id": ORG,
                      "query_text": "what does the user prefer",
                      "limit": 10, "rerank": False},
                headers=headers,
            )

        try:
            fmt("retrieve (rerank=false)", timeit(retrieve_norerank, n=5))
        except Exception as exc:  # noqa: BLE001
            print(f"  failed: {str(exc)[:200]}")


if __name__ == "__main__":
    main()
