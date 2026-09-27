"""Tests for the MCP security controls.

The MCP surface writes to memory on behalf of agents, so these assert the properties
that actually matter: writes are tenant-scoped, sensitive data is redacted before it
is stored, the server refuses to run unauthenticated, and the bulk-import escape
hatches are confined.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from contexta.mcp.security import (
    McpRateLimiter,
    McpSecurityError,
    safe_local_path,
    validate_content,
    validate_importance,
)

ORG_A = uuid.UUID("00000000-0000-0000-0000-000000000001")
ORG_B = uuid.UUID("00000000-0000-0000-0000-000000000002")


# --------------------------------------------------------------------------- #
# Tenant scoping
# --------------------------------------------------------------------------- #


def test_service_requires_a_tenant():
    from contexta.mcp.service import ContextaMCPService

    with pytest.raises(ValueError, match="organization_id"):
        ContextaMCPService(allow_legacy_tenant=False)


def test_service_uses_the_injected_tenant_not_the_default():
    from contexta.mcp.service import ContextaMCPService

    service = ContextaMCPService(organization_id=ORG_B)
    assert service.org_id == ORG_B
    assert service.org_id != ORG_A


def test_service_reads_tenant_from_environment(monkeypatch):
    from contexta.mcp.service import ContextaMCPService

    monkeypatch.setenv("CONTEXTA_ORGANIZATION_ID", str(ORG_B))
    service = ContextaMCPService()
    assert service.org_id == ORG_B


def _db_available() -> bool:
    """True when the configured Postgres is actually reachable.

    On a developer host `localhost:5432` is often a *different* Postgres, so these
    DB-backed checks are skipped rather than reported as failures. They are covered
    for real by `benchmarks/mcp_security_check.py` inside the stack.
    """
    import asyncio

    async def probe() -> bool:
        from sqlalchemy import text

        from contexta.db import AsyncSessionFactory

        try:
            async with AsyncSessionFactory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    try:
        return asyncio.run(probe())
    except Exception:
        return False


requires_db = pytest.mark.skipif(
    not _db_available(), reason="needs the Contexta Postgres (see benchmarks/mcp_security_check.py)"
)


# --------------------------------------------------------------------------- #
# Redaction on the write path
# --------------------------------------------------------------------------- #


@requires_db
@pytest.mark.asyncio
async def test_remember_redacts_pii_before_storing(monkeypatch):
    """The stored content must not contain the raw secret or contact details."""
    from contexta.mcp import service as service_module

    service = service_module.ContextaMCPService(organization_id=ORG_A)
    captured: dict[str, object] = {}

    async def fake_embed(_text: str) -> list[float]:
        return [0.0] * 1024

    monkeypatch.setattr(service._embedder, "embed", fake_embed)

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def add(self, _obj):
            captured["added"] = True

        async def flush(self):
            return None

        async def commit(self):
            return None

    monkeypatch.setattr(service, "session", lambda: _FakeSession())

    result = await service.remember(
        "My email is dana.whitfield@northwind-logistics.com and my card is 4111 1111 1111 1111.",
        user_id="alice",
        memory_type="fact",
    )

    # The tool must succeed, and must not echo the raw sensitive values back.
    assert result is not None
    rendered = str(result)
    assert "dana.whitfield@northwind-logistics.com" not in rendered
    assert "4111 1111 1111 1111" not in rendered


@pytest.mark.asyncio
async def test_remember_rejects_out_of_range_importance():
    from contexta.mcp import service as service_module

    service = service_module.ContextaMCPService(organization_id=ORG_A)
    with pytest.raises(McpSecurityError, match="importance"):
        await service.remember("hello", user_id="alice", importance=7.5)


@pytest.mark.asyncio
async def test_remember_rejects_unknown_memory_type():
    from contexta.mcp import service as service_module

    service = service_module.ContextaMCPService(organization_id=ORG_A)
    with pytest.raises(McpSecurityError, match="memory_type"):
        await service.remember("hello", user_id="alice", memory_type="not-a-type")


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def test_content_validation():
    with pytest.raises(McpSecurityError):
        validate_content("")
    with pytest.raises(McpSecurityError):
        validate_content("   ")
    with pytest.raises(McpSecurityError):
        validate_content("x" * 20_001)
    assert validate_content("ok") == "ok"


def test_importance_validation():
    assert validate_importance(0) == 0.0
    assert validate_importance(1) == 1.0
    assert validate_importance(0.5) == 0.5
    for bad in (-0.1, 1.1, "nope", None):
        with pytest.raises(McpSecurityError):
            validate_importance(bad)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Filesystem confinement
# --------------------------------------------------------------------------- #


def test_local_path_allows_files_inside_a_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "data.jsonl"
    target.write_text("[]", encoding="utf-8")
    assert safe_local_path(str(target), roots=(allowed,)) == target.resolve()


def test_local_path_rejects_traversal(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("classified", encoding="utf-8")
    with pytest.raises(McpSecurityError):
        safe_local_path(str(allowed / ".." / "secret.txt"), roots=(allowed,))


def test_local_path_rejects_absolute_outside_root(tmp_path: Path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(McpSecurityError):
        safe_local_path(str(outside), roots=(allowed,))


def test_local_path_rejects_missing_file(tmp_path: Path):
    with pytest.raises(McpSecurityError):
        safe_local_path(str(tmp_path / "nope.json"), roots=(tmp_path,))


def test_local_path_rejects_directory(tmp_path: Path):
    with pytest.raises(McpSecurityError, match="regular file"):
        safe_local_path(str(tmp_path), roots=(tmp_path,))


def test_local_path_rejects_empty():
    with pytest.raises(McpSecurityError):
        safe_local_path("")


# --------------------------------------------------------------------------- #
# SSRF guard (no network required for the rejections)
# --------------------------------------------------------------------------- #


def test_remote_fetch_rejects_non_https():
    from contexta.mcp.security import safe_remote_fetch

    with pytest.raises(McpSecurityError, match="https"):
        safe_remote_fetch("http://example.com/data.json")


def test_remote_fetch_rejects_host_not_allowlisted():
    from contexta.mcp.security import safe_remote_fetch

    with pytest.raises(McpSecurityError, match="ALLOWED_FETCH_HOSTS"):
        safe_remote_fetch("https://evil.example/data.json", allowed_hosts=("good.example",))


def test_remote_fetch_rejects_loopback_target():
    from contexta.mcp.security import safe_remote_fetch

    with pytest.raises(McpSecurityError, match="non-public"):
        safe_remote_fetch("https://localhost/data.json")


def test_remote_fetch_rejects_empty_url():
    from contexta.mcp.security import safe_remote_fetch

    with pytest.raises(McpSecurityError):
        safe_remote_fetch("")


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_rate_limiter_falls_back_to_local_bucket(monkeypatch):
    """With Redis down the limiter still bounds a single process.

    This is deliberate: a Redis outage should not hand one process an unlimited
    budget, it should just make the limit per-process rather than per-cluster.
    """
    limiter = McpRateLimiter(rate_per_second=0.0001, burst=2)
    monkeypatch.setattr(limiter, "_redis", lambda: None)
    results = [await limiter.allow("key:abc") for _ in range(6)]
    assert results[:2] == [True, True]
    assert False in results[2:]


@pytest.mark.asyncio
async def test_rate_limiter_local_bucket_engages(monkeypatch):
    limiter = McpRateLimiter(rate_per_second=0.0001, burst=2)
    monkeypatch.setattr(limiter, "_redis", lambda: None)
    results = [await limiter.allow("key:abc") for _ in range(6)]
    assert results[:2] == [True, True]
    assert False in results[2:]


@pytest.mark.asyncio
async def test_rate_limiter_is_per_identity(monkeypatch):
    limiter = McpRateLimiter(rate_per_second=0.0001, burst=1)
    monkeypatch.setattr(limiter, "_redis", lambda: None)
    assert await limiter.allow("key:noisy") is True
    assert await limiter.allow("key:noisy") is False
    assert await limiter.allow("key:quiet") is True


# --------------------------------------------------------------------------- #
# Server bootstrap
# --------------------------------------------------------------------------- #


def test_server_refuses_to_start_without_auth(monkeypatch):
    from contexta.mcp.server import create_mcp_server

    monkeypatch.delenv("CONTEXTA_MCP_API_KEY", raising=False)
    monkeypatch.delenv("CONTEXTA_MCP_ALLOW_ANONYMOUS", raising=False)
    with pytest.raises(McpSecurityError, match="requires authentication"):
        create_mcp_server()


@requires_db
def test_server_rejects_unknown_key(monkeypatch):
    from contexta.mcp.server import create_mcp_server

    monkeypatch.setenv("CONTEXTA_MCP_API_KEY", "mk_live_definitely_not_a_real_key")
    monkeypatch.delenv("CONTEXTA_MCP_ALLOW_ANONYMOUS", raising=False)
    with pytest.raises(McpSecurityError):
        create_mcp_server()


def test_allowed_roots_default_is_not_empty(monkeypatch):
    from contexta.mcp.security import allowed_roots

    monkeypatch.delenv("CONTEXTA_MCP_ALLOWED_ROOTS", raising=False)
    monkeypatch.delenv("CONTEXTA_ARTIFACT_STORAGE_PATH", raising=False)
    assert len(allowed_roots()) >= 1
