"""Is the running model server producing real 1024-dim vectors, or zero-padded ones?"""

import httpx

with httpx.Client(timeout=120.0) as client:
    r = client.post(
        "http://localhost:8001/v1/embeddings",
        json={"input": ["hello world"], "model": "Qwen/Qwen3-Embedding-0.6B"},
    )
    vec = r.json()["data"][0]["embedding"]
    print("dims:", len(vec))
    nonzero = sum(1 for v in vec if abs(v) > 1e-9)
    print("non-zero dims:", nonzero)
    print("zero dims    :", len(vec) - nonzero)
    # Where does the vector become zero? That reveals a padded tail.
    last_nonzero = max((i for i, v in enumerate(vec) if abs(v) > 1e-9), default=-1)
    print("last non-zero index:", last_nonzero)
    if last_nonzero < len(vec) - 1:
        tail = vec[last_nonzero + 1:]
        print(f"PADDED TAIL: {len(tail)} trailing dims are all zero")
    else:
        print("no zero padding detected")
    print("norm:", round(sum(v * v for v in vec) ** 0.5, 6))
    print("first 8:", [round(v, 5) for v in vec[:8]])

    h = client.get("http://localhost:8001/health").json()
    print("\nhealth backend:", h.get("backend"))
    print("full health:", {k: v for k, v in h.items() if k not in {"timestamp"}})
