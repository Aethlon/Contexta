"""Security controls for the MCP surface.

The MCP server is how AI agents write to memory, so it is held to the same bar as
the REST API. Before this module it had none of it: no authentication, no redaction,
a hard-coded tenant, and two tools that accepted an arbitrary filesystem path and an
arbitrary URL.

Controls provided here:

* :func:`resolve_tenant` - API-key verification against the same table the REST API
  uses, so an MCP caller is scoped exactly like an HTTP caller.
* :func:`safe_local_path` - confines `file_path` to configured roots, rejecting
  traversal, symlink escapes and non-regular files.
* :func:`safe_remote_fetch` - SSRF guard for `file_url`: https only, host allowlist,
  DNS results checked against private/loopback/link-local ranges, redirect cap and a
  hard byte limit.
* :class:`McpRateLimiter` - per-key token bucket, fail-open.

Everything except :func:`resolve_tenant` is pure and unit-testable without a database
or network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import socket
import threading
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONTENT_CHARS = 20_000
DEFAULT_MAX_FILE_BYTES = 50 * 1024 * 1024
DEFAULT_FETCH_TIMEOUT_SECONDS = 30.0
MAX_REDIRECTS = 3


class McpSecurityError(PermissionError):
    """Raised when a request violates an MCP security control."""


@dataclass(frozen=True)
class TenantContext:
    """Resolved identity for an MCP caller."""

    organization_id: str
    actor_id: str
    key_id: str
    scopes: tuple[str, ...]
    tier: str = "standard"


# --------------------------------------------------------------------------- #
# Local filesystem access
# --------------------------------------------------------------------------- #


def allowed_roots() -> tuple[Path, ...]:
    """Directories `file_path` may read from.

    Defaults to the current working directory and the artifacts store. Set
    ``CONTEXTA_MCP_ALLOWED_ROOTS`` (os.pathsep separated) to widen deliberately.
    """
    raw = os.environ.get("CONTEXTA_MCP_ALLOWED_ROOTS", "").strip()
    if raw:
        candidates = [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]
    else:
        candidates = [Path.cwd()]
        artifacts = os.environ.get("CONTEXTA_ARTIFACT_STORAGE_PATH", "").strip()
        if artifacts:
            candidates.append(Path(artifacts).expanduser())
    return tuple(candidates)


def safe_local_path(candidate: str, *, roots: tuple[Path, ...] | None = None) -> Path:
    """Resolve ``candidate`` and prove it stays inside an allowed root.

    Rejects absolute paths outside the roots, ``..`` traversal, and symlinks that
    resolve outside the roots.
    """
    if not candidate or not candidate.strip():
        raise McpSecurityError("file_path must not be empty")
    permitted = roots if roots is not None else allowed_roots()
    if not permitted:
        raise McpSecurityError("No MCP filesystem roots are configured.")

    target = Path(candidate).expanduser()
    # Resolve the candidate itself, then each root, so a symlink cannot be used to
    # escape the root after the check.
    try:
        resolved = target.resolve(strict=True)
    except FileNotFoundError as exc:
        raise McpSecurityError(f"file_path does not exist: {candidate}") from exc
    except OSError as exc:
        raise McpSecurityError(f"file_path could not be resolved: {exc}") from exc

    for root in permitted:
        try:
            root_resolved = root.resolve(strict=False)
        except OSError:
            continue
        if resolved == root_resolved or root_resolved in resolved.parents:
            if not resolved.is_file():
                raise McpSecurityError("file_path must reference a regular file")
            return resolved

    raise McpSecurityError(
        f"file_path is outside the permitted roots ({[str(r) for r in permitted]})"
    )


# --------------------------------------------------------------------------- #
# Remote fetch (SSRF guard)
# --------------------------------------------------------------------------- #


def _is_public_address(host: str) -> bool:
    """True when every address `host` resolves to is publicly routable."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise McpSecurityError(f"Could not resolve host {host!r}") from exc
    if not infos:
        raise McpSecurityError(f"Host {host!r} did not resolve to any address")
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise McpSecurityError(f"Host {host!r} resolved to an invalid address") from exc
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise McpSecurityError(
                f"Refusing to fetch {host!r}: resolves to non-public address {address}"
            )
    return True


def safe_remote_fetch(
    url: str,
    *,
    allowed_hosts: tuple[str, ...] | None = None,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    timeout: float = DEFAULT_FETCH_TIMEOUT_SECONDS,
) -> bytes:
    """Fetch a remote dataset with SSRF protections.

    Requires https, validates the host against an allowlist when one is configured,
    re-checks DNS after every redirect, and stops at ``max_bytes``.
    """
    import httpx

    if not url or not url.strip():
        raise McpSecurityError("file_url must not be empty")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise McpSecurityError("file_url must use https")
    host = parsed.hostname
    if not host:
        raise McpSecurityError("file_url has no host")

    hosts = allowed_hosts
    if hosts is None:
        raw = os.environ.get("CONTEXTA_MCP_ALLOWED_FETCH_HOSTS", "").strip()
        hosts = tuple(part.strip().lower() for part in raw.split(",") if part.strip()) or None
    if hosts is not None:
        allowed = {h.lower() for h in hosts}
        if host.lower() not in allowed:
            raise McpSecurityError(
                f"Host {host!r} is not in CONTEXTA_MCP_ALLOWED_FETCH_HOSTS"
            )
    _is_public_address(host)

    current = url.strip()
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            response = client.get(current)
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise McpSecurityError("Redirect without a location header")
                current = str(httpx.URL(current).join(location))
                redirect_host = urlparse(current).hostname
                if not redirect_host:
                    raise McpSecurityError("Redirect target has no host")
                if hosts is not None and redirect_host.lower() not in {h.lower() for h in hosts}:
                    raise McpSecurityError(
                        f"Redirect to disallowed host {redirect_host!r}"
                    )
                _is_public_address(redirect_host)
                continue
            response.raise_for_status()
            content = response.content
            if len(content) > max_bytes:
                raise McpSecurityError(
                    f"Remote dataset is larger than the {max_bytes} byte limit"
                )
            return content
    raise McpSecurityError("Too many redirects while fetching file_url")


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #


T = TypeVar("T")


def run_coroutine_blocking(coro: Coroutine[Any, Any, T]) -> T:
    """Run `coro` to completion from synchronous code, running loop or not.

    ``asyncio.run`` cannot be called while a loop is already running in this
    thread, which is exactly the situation the MCP bootstrap is in whenever it is
    embedded in an async app (a FastAPI lifespan, a test, a parent agent's
    server). Handing the coroutine to a worker thread that owns its own loop keeps
    the synchronous entrypoints working; the shared engine uses ``NullPool``, so a
    session opened on the worker loop is not bound to the caller's loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    outcome: list[tuple[bool, Any]] = []

    def _worker() -> None:
        try:
            outcome.append((True, asyncio.run(coro)))
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread
            outcome.append((False, exc))

    thread = threading.Thread(target=_worker, name="contexta-mcp-bootstrap", daemon=True)
    thread.start()
    thread.join()
    succeeded, value = outcome[0]
    if not succeeded:
        raise value
    return value


async def resolve_tenant_async(api_key: str) -> TenantContext | None:
    """Resolve an MCP API key to a tenant, using the REST API's key store.

    Returns None for an unknown or revoked key. Raises on infrastructure failure so
    a database outage is not mistaken for a bad key.
    """
    from sqlalchemy import select

    from contexta.db import AsyncSessionFactory
    from contexta.models.api_key import ApiKeyRecord

    if not api_key or not api_key.strip():
        return None
    token_hash = ApiKeyRecord.hash_token(api_key.strip()) if hasattr(
        ApiKeyRecord, "hash_token"
    ) else _hash_token(api_key.strip())

    async with AsyncSessionFactory() as session:
        record = (
            await session.execute(
                select(ApiKeyRecord).where(ApiKeyRecord.token_hash == token_hash)
            )
        ).scalar_one_or_none()
        if record is None or record.revoked_at is not None:
            return None
        return TenantContext(
            organization_id=str(record.organization_id),
            actor_id=str(record.actor_id),
            key_id=str(record.id),
            scopes=tuple(record.scopes or ()),
            tier=str(getattr(record, "tier", None) or "standard"),
        )


def resolve_tenant(api_key: str) -> TenantContext | None:
    """Synchronous wrapper over :func:`resolve_tenant_async`."""
    if not api_key or not api_key.strip():
        return None
    return run_coroutine_blocking(resolve_tenant_async(api_key))


def _hash_token(token: str) -> str:
    import hashlib

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_scope(context: TenantContext, *needed: str) -> None:
    """Raise unless the key carries one of `needed` (admin implies all)."""
    if "admin" in context.scopes:
        return
    if not any(scope in context.scopes for scope in needed):
        raise McpSecurityError(
            f"API key is missing a required scope (one of: {', '.join(needed)})"
        )


# --------------------------------------------------------------------------- #
# Rate limiting
# --------------------------------------------------------------------------- #


class McpRateLimiter:
    """Token bucket per identity. Fail-open: a Redis outage must not block agents."""

    def __init__(self, rate_per_second: float = 20.0, burst: float = 40.0) -> None:
        self.rate = rate_per_second
        self.burst = burst
        self._client: Any = None
        self._disabled = False
        self._local: dict[str, tuple[float, float]] = {}

    def _redis(self):
        if self._disabled:
            return None
        if self._client is None:
            try:
                import redis.asyncio as aioredis

                from contexta.config.settings import get_settings

                self._client = aioredis.from_url(get_settings().redis_url)
            except Exception:  # noqa: BLE001 - degrade to local buckets, never crash
                logger.debug("MCP rate limiter: Redis unavailable, using local buckets")
                self._disabled = True
                return None
        return self._client

    async def allow(self, identity: str, cost: float = 1.0) -> bool:
        client = self._redis()
        if client is not None:
            return await self._allow_redis(client, identity, cost)
        return self._allow_local(identity, cost)

    async def _allow_redis(self, client, identity: str, cost: float) -> bool:
        now = time.time()
        try:
            key = f"mcp:rl:{identity}"
            async with client.pipeline(transaction=True) as pipe:
                pipe.get(f"{key}:ts")
                pipe.get(f"{key}:tokens")
                previous_ts, previous_tokens = await pipe.execute()
                if previous_ts is None:
                    available = self.burst
                else:
                    elapsed = max(0.0, now - float(previous_ts))
                    available = min(
                        self.burst, float(previous_tokens or self.burst) + elapsed * self.rate
                    )
                allowed = available >= cost
                remaining = available - cost if allowed else available
                pipe.set(f"{key}:tokens", remaining)
                pipe.expire(f"{key}:tokens", 120)
                pipe.set(f"{key}:ts", now)
                pipe.expire(f"{key}:ts", 120)
                await pipe.execute()
            return allowed
        except Exception:
            logger.debug("MCP rate limiter Redis error; allowing", exc_info=True)
            return True

    def _allow_local(self, identity: str, cost: float) -> bool:
        now = time.time()
        last, tokens = self._local.get(identity, (now, self.burst))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        allowed = tokens >= cost
        if allowed:
            tokens -= cost
        self._local[identity] = (now, tokens)
        if len(self._local) > 10_000:
            self._local = {
                key: value for key, value in self._local.items() if now - value[0] < 300
            }
        return allowed


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def validate_content(content: str, *, max_chars: int = DEFAULT_MAX_CONTENT_CHARS) -> str:
    """Reject empty or oversized memory content."""
    if content is None:
        raise McpSecurityError("content is required")
    text = content if isinstance(content, str) else str(content)
    if not text.strip():
        raise McpSecurityError("content must not be empty")
    if len(text) > max_chars:
        raise McpSecurityError(
            f"content is {len(text)} characters, over the {max_chars} limit"
        )
    return text


def validate_importance(importance: float) -> float:
    """Clamp-free validation: importance must be a number in [0, 1]."""
    try:
        value = float(importance)
    except (TypeError, ValueError) as exc:
        raise McpSecurityError("importance must be a number between 0 and 1") from exc
    if not 0.0 <= value <= 1.0:
        raise McpSecurityError("importance must be between 0 and 1")
    return value


__all__ = [
    "DEFAULT_MAX_CONTENT_CHARS",
    "DEFAULT_MAX_FILE_BYTES",
    "McpRateLimiter",
    "McpSecurityError",
    "TenantContext",
    "allowed_roots",
    "require_scope",
    "resolve_tenant",
    "resolve_tenant_async",
    "run_coroutine_blocking",
    "safe_local_path",
    "safe_remote_fetch",
    "validate_content",
    "validate_importance",
]
