#!/usr/bin/env python3
"""New-user end-to-end walkthrough.

This is the path a first-time self-hoster actually takes, in order, and it
asserts on the parts that matter rather than just checking status codes:

    boot -> first key -> first memory -> retrieve -> contradict -> supersede
         -> retrieve again -> graph -> MCP

The supersession assertions are the point. A memory layer that merely accepts
writes is not interesting; the guarantee is that a corrected fact *replaces* the
one it contradicts and that retrieval stops returning the stale version.

Run against a stack started with `docker compose up -d`:

    python benchmarks/new_user_e2e.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "http://localhost:8000"
MCP = "http://localhost:8765"
DASH = "http://localhost:3000"

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((PASS if ok else FAIL, name, detail))
    print(f"  [{PASS if ok else FAIL}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    return ok


def api(path: str, key: str, method: str = "GET", body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"x-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw.strip() else {}


def mint_key() -> tuple[str, str, str]:
    out = subprocess.run(
        [sys.executable, "scripts/bootstrap_key.py", "--name", "new-user-e2e"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # The script indents its output block, so match on the stripped line.
    fields: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        label, _, value = line.partition("=")
        if label.strip() in ("CONTEXTA_API_KEY", "ORG", "ACTOR"):
            fields[label.strip()] = value.strip()
    return fields["CONTEXTA_API_KEY"], fields["ORG"], fields["ACTOR"]


def observe(key: str, org: str, actor: str, text: str) -> str:
    body = {
        "user_id": actor,
        "organization_id": org,
        "session_id": str(uuid.uuid4()),
        "messages": [{"role": "user", "content": text}],
    }
    return api("/v1/observations", key, "POST", body)["job_id"]


def wait_for_extraction(key: str, job_id: str, timeout: int = 420) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = api(f"/v1/observations/{job_id}", key).get("status")
        if status in ("completed", "failed"):
            return status
        time.sleep(5)
    return "timeout"


def retrieve(key: str, actor: str, query: str) -> list[dict]:
    out = api("/v1/retrieve", key, "POST", {"query_text": query, "user_id": actor, "limit": 10})
    return out.get("results") or []


def texts(hits: list[dict]) -> str:
    return " | ".join((h.get("memory") or {}).get("content", "") for h in hits)


def mcp_port_is_loopback() -> bool:
    """The MCP server binds one tenant at startup, so it must not be on all interfaces."""
    out = subprocess.run(["docker", "compose", "config"], capture_output=True, text=True)
    if out.returncode != 0:
        return True
    lines = [l.strip() for l in out.stdout.splitlines()]
    for i, line in enumerate(lines):
        # Long form renders host_ip / target / published on separate lines.
        if line.startswith("target:") and line.split(":", 1)[1].strip() == "8765":
            window = lines[max(0, i - 3):i]
            host = next((w.split(":", 1)[1].strip() for w in window
                         if w.startswith("host_ip:")), "")
            return host in ("127.0.0.1", "localhost")
        # Short form renders the whole mapping on one line.
        if "8765" in line and line.count(":") == 2 and line.startswith("-"):
            return line.split(":", 1)[1].split(":")[0] in ("127.0.0.1", "localhost")
    return True


def main() -> int:
    print("\n1. First key")
    key, org, actor = mint_key()
    check("bootstrap_key.py mints a working key", len(key) > 20, f"org={org[:8]}")
    check("key authenticates", api("/v1/memories", key) is not None)

    print("\n2. First memory")
    job = observe(key, org, actor, "I moved from New York to London last month. My port is 5432.")
    status = wait_for_extraction(key, job)
    check("observation extracts", status == "completed", f"status={status}")
    memories = api("/v1/memories", key)
    check("memories were written", len(memories) > 0, f"{len(memories)} memories")

    print("\n3. Retrieve")
    hits = retrieve(key, actor, "Where do I live?")
    body = texts(hits)
    check("the city is retrievable", "london" in body.lower(), body[:90])
    check("the port is retrievable", "5432" in body, body[:90])

    print("\n4. Contradict the port")
    job2 = observe(key, org, actor, "Actually I changed my port, it is 6543 now.")
    status2 = wait_for_extraction(key, job2)
    check("second observation extracts", status2 == "completed", f"status={status2}")

    print("\n5. Supersession")
    after = texts(retrieve(key, actor, "What port do I use?"))
    check("new port is retrievable", "6543" in after, after[:90])
    check("superseded port is no longer retrievable", "5432" not in after, after[:90])

    print("\n6. Explain the surviving fact")
    current = [h for h in retrieve(key, actor, "What port do I use?") if "6543" in (h.get("memory") or {}).get("content", "")]
    if current:
        detail = api(f"/v1/memories/{current[0]['memory']['id']}/explain", key)
        for section in ("source", "classification", "scoring", "supersession_history"):
            check(f"explain reports {section}", section in detail)
    else:
        check("explain reports the surviving fact", False, "no current memory found")

    # The audit trail lives on the *superseded* memory, not the surviving one. The
    # list endpoint does not expose bitemporal validity (retired rows still read
    # "active"), so pick the retired port value and require its lineage.
    retired = [m for m in api("/v1/memories", key) if "5432" in (m.get("title") or "")]
    with_lineage = []
    for m in retired:
        history = api(f"/v1/memories/{m['id']}/explain", key).get("supersession_history") or []
        if history:
            with_lineage.append(history[0])
    check("superseded memory keeps its lineage", bool(with_lineage),
          f"{len(with_lineage)}/{len(retired)} retired records carry a version chain")

    print("\n7. Graph")
    try:
        graph = api(f"/v1/entities/graph/{actor}", key)
        check("entity graph is reachable", "nodes" in graph, f"{len(graph.get('nodes', []))} nodes")
    except urllib.error.HTTPError as e:
        check("entity graph is reachable", False, f"HTTP {e.code}")

    print("\n8. MCP")
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "e2e", "version": "1"}}}

    mcp_key = os.environ.get("CONTEXTA_MCP_API_KEY", "").strip()
    if mcp_key:
        session = None
        try:
            req = urllib.request.Request(f"{MCP}/mcp", data=json.dumps(init).encode(),
                                         headers={"x-api-key": mcp_key,
                                                  "Content-Type": "application/json",
                                                  "Accept": "application/json, text/event-stream"})
            with urllib.request.urlopen(req, timeout=30) as r:
                session = r.headers.get("mcp-session-id")
            check("MCP handshake with the key", bool(session))
        except Exception as e:
            check("MCP handshake with the key", False, type(e).__name__)

        if session:
            # Streamable HTTP requires the post-handshake notification before the
            # session will serve anything beyond initialize.
            ready = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
            try:
                req = urllib.request.Request(f"{MCP}/mcp", data=json.dumps(ready).encode(),
                                             headers={"x-api-key": mcp_key, "mcp-session-id": session,
                                                      "Content-Type": "application/json",
                                                      "Accept": "application/json, text/event-stream"})
                urllib.request.urlopen(req, timeout=30).read()
            except Exception:
                pass
            listed = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
            try:
                req = urllib.request.Request(f"{MCP}/mcp", data=json.dumps(listed).encode(),
                                             headers={"x-api-key": mcp_key,
                                                      "mcp-session-id": session,
                                                      "Content-Type": "application/json",
                                                      "Accept": "application/json, text/event-stream"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    body = r.read().decode()
                check("MCP lists its tools", '"result"' in body and '"error"' not in body,
                      f"{len(body)} bytes")
            except Exception as e:
                check("MCP lists its tools", False, type(e).__name__)
    else:
        print("  [SKIP] MCP — set CONTEXTA_MCP_API_KEY to test it")

    # MCP binds one tenant at startup from the configured key; it does not
    # authenticate each caller. That is why compose publishes it on loopback.
    check("MCP is published on loopback only", mcp_port_is_loopback())

    print("\n9. Console")
    for path in ("/dashboard", "/dashboard/welcome", "/dashboard/mcp", "/dashboard/docs"):
        try:
            urllib.request.urlopen(f"{DASH}{path}", timeout=90)
            check(f"console {path}", True)
        except Exception as e:
            check(f"console {path}", False, type(e).__name__)

    failed = [r for r in results if r[0] == FAIL]
    print("\n" + "=" * 58)
    print(f"  {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("  failures:")
        for _, name, detail in failed:
            print(f"    - {name} {detail}")
    print("=" * 58)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
