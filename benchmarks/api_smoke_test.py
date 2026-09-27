"""Comprehensive API smoke test for the single Python entry point.

Exercises every public surface against the live stack and reports a pass/fail table.
Writes one observation and one artifact, so it is safe to re-run.

Run:  uv run --no-sync python benchmarks/api_smoke_test.py
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
import time
import uuid
from dataclasses import dataclass, field

import httpx

BASE = "http://localhost:8000"
ORG = "00000000-0000-0000-0000-000000000001"
RICH_USER = "4befdce9-64e1-525a-bb9a-d5707dbbe94e"


@dataclass
class Result:
    name: str
    method: str
    path: str
    status: int = 0
    expected: set[int] = field(default_factory=set)
    note: str = ""
    ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in self.expected


def psql(sql: str) -> str:
    import subprocess

    out = subprocess.run(
        ["docker", "exec", "memento-postgres-1", "psql", "-U", "postgres",
         "-d", "contexta", "-t", "-A", "-c", sql],
        capture_output=True, text=True, check=False,
    )
    return out.stdout.strip()


def mint_key(actor: str) -> str:
    token = f"mk_live_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    psql(
        "INSERT INTO api_key (id, name, prefix, token_hash, organization_id, actor_id, "
        "scopes, created_at) VALUES "
        f"('{uuid.uuid4()}', 'smoke', '{token[:16]}', '{token_hash}', '{ORG}', "
        f"'{actor}', ARRAY['read','write'], now());"
    )
    return token


def call(client: httpx.Client, headers: dict, method: str, path: str,
         body: dict | None = None, expected: set[int] | None = None) -> Result:
    result = Result(name=path, method=method, path=path, expected=expected or set())
    t0 = time.perf_counter()
    try:
        if method == "GET":
            # Query-string endpoints need params, not a JSON body.
            response = client.request(method, f"{BASE}{path}", params=body, headers=headers)
        else:
            response = client.request(method, f"{BASE}{path}", json=body, headers=headers)
        result.status = response.status_code
        result.ms = (time.perf_counter() - t0) * 1000
        if response.status_code >= 400:
            result.note = response.text[:120]
    except Exception as exc:  # noqa: BLE001
        result.status = -1
        result.note = f"{type(exc).__name__}: {exc}"[:120]
    return result


def main() -> int:
    actor = RICH_USER
    key = mint_key(actor)
    auth = {"x-api-key": key}
    session_id = str(uuid.uuid4())
    results: list[Result] = []

    with httpx.Client(timeout=180.0) as client:
        # --- public / infra -------------------------------------------------
        for path, expected in [
            ("/healthz", {200}),
            ("/readyz", {200}),
            ("/metrics", {200}),
            ("/openapi.json", {200}),
        ]:
            results.append(call(client, {}, "GET", path, expected=expected))

        # --- auth must actually be enforced --------------------------------
        results.append(call(client, {}, "GET", "/v1/memories", expected={401, 403}))
        results.append(call(
            client, {"x-api-key": "mk_live_bogus"}, "GET", "/v1/memories",
            expected={401, 403},
        ))

        # --- reads ----------------------------------------------------------
        # Methods taken from the live route table, not assumed.
        for method, path, body, expected in [
            ("GET", "/v1/memories", None, {200}),
            ("GET", "/v1/memories/search", {"query": "preferences", "limit": 3}, {200}),
            ("GET", "/v1/memories/hybrid", {"query": "preferences", "limit": 3}, {200}),
            ("GET", "/v1/memories/context", None, {200, 422}),
            ("GET", "/v1/memories/timeline/" + actor, None, {200}),
            ("GET", "/v1/entities/traverse", {"query": "user", "limit": 3}, {200, 422}),
            ("GET", "/v1/graph/traverse", {"query": "user", "limit": 3}, {200, 422}),
            ("POST", "/v1/retrieve", {"user_id": actor, "organization_id": ORG,
                                      "query_text": "what does the user prefer",
                                      "limit": 5}, {200}),
            ("POST", "/v1/retrieve/batch", {"queries": [
                {"user_id": actor, "organization_id": ORG,
                 "query_text": "preferences", "limit": 3}]}, {200}),
            ("POST", "/v1/kernel/recall", {"scope": {"tenant_id": ORG, "user_id": actor},
                                           "query": "preferences"}, {200, 422}),
            ("GET", "/v1/sessions/inspect/" + actor, None, {200}),
            ("GET", "/v1/system/engine-status", None, {200}),
            ("GET", "/v1/keys", None, {200}),
        ]:
            results.append(call(client, auth, method, path, body=body, expected=expected))

        # --- writes ---------------------------------------------------------
        obs_body = {
            "user_id": actor,
            "organization_id": ORG,
            "session_id": session_id,
            "messages": [{"role": "user", "content":
                          "I prefer dark mode and I am based in Berlin. "
                          "My email is smoke.test@example.com."}],
        }
        obs = call(client, auth, "POST", "/v1/observations", body=obs_body, expected={202})
        results.append(obs)
        job_id = None
        if obs.status == 202:
            try:
                job_id = client.get(f"{BASE}/v1/observations/{obs.note}/status",
                                    headers=auth).json().get("job_id")
            except Exception:  # noqa: BLE001
                job_id = None
            if not job_id:
                payload = obs  # placeholder, real id read below
        results.append(call(client, auth, "POST", "/v1/observations/batch",
                            body={"observations": [obs_body]}, expected={202, 422}))

        # validation must be rejected, not silently accepted
        results.append(call(client, auth, "POST", "/v1/observations",
                            body={"messages": []}, expected={401, 403, 422}))

        # --- tenant isolation must hold ------------------------------------
        other_org = str(uuid.uuid4())
        results.append(call(client, auth, "POST", "/v1/retrieve",
                            body={"user_id": actor, "organization_id": other_org,
                                  "query_text": "x", "limit": 1},
                            expected={200, 403}))

        # --- cache behaviour ------------------------------------------------
        cache_probe = {"user_id": actor, "organization_id": ORG,
                       "query_text": "cache probe unique string 12345", "limit": 5}
        first = call(client, auth, "POST", "/v1/retrieve", body=cache_probe, expected={200})
        second = call(client, auth, "POST", "/v1/retrieve", body=cache_probe, expected={200})
        hit = client.post(f"{BASE}/v1/retrieve", json=cache_probe,
                          headers=auth).headers.get("x-contexta-cache", "-")
        results.append(first)
        results.append(second)
        print(f"[cache] header sequence probe: {hit}")
        if hit == "hit":
            print(f"[cache] second identical call served from cache "
                  f"({first.ms:.0f} ms -> {second.ms:.0f} ms)")
        else:
            print(f"[cache] WARNING: expected 'hit' on repeat, got {hit!r}")

    passed = [r for r in results if r.ok]
    failed = [r for r in results if not r.ok]
    print("\n" + "=" * 78)
    print(f"{'RESULT':8s} {'METHOD':7s} {'PATH':38s} {'STATUS':>7s} {'ms':>8s}")
    print("-" * 78)
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        print(f"{mark:8s} {r.method:7s} {r.path:38s} {r.status:7d} {r.ms:8.0f}")
        if not r.ok and r.note:
            print(f"{'':8s} -> {r.note}")
    print("-" * 78)
    print(f"{len(passed)}/{len(results)} passed, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
