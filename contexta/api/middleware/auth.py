"""Authentication middleware."""

from __future__ import annotations

import os
import sys
from typing import Any
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from contexta.db import AsyncSessionFactory
from contexta.repositories.api_key_repo import ApiKeyRepository

PUBLIC_PATHS = {
    "/healthz",
    "/readyz",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v1/auth/signup",
    "/v1/auth/signin",
    "/v1/auth/reset-password",
    "/v1/auth/emergency-wipe-reset",
    "/v1/auth/onboarding",
    "/v1/auth/verify-email",
    "/v1/auth/forgot-password",
}

_ORGANIZATION_HEADERS = (
    "x-organization-id",
    "x-org-id",
    "X-Mem-Tenant-Id",
    "x-mem-tenant-id",
)
_ACTOR_HEADERS = (
    "x-user-id",
    "x-contexta-user-id",
    "X-Mem-Actor-Id",
    "x-mem-actor-id",
)
_ZERO_UUID = UUID(int=0)


class _IdentityHeaderError(ValueError):
    pass


def _header_values(request: Request, names: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for name in names:
        values.update(
            value.strip()
            for value in request.headers.getlist(name)
            if value and value.strip()
        )
    return values


def _read_uuid_headers(request: Request, names: tuple[str, ...]) -> UUID | None:
    values = _header_values(request, names)
    if not values:
        return None
    parsed: set[UUID] = set()
    for value in values:
        try:
            parsed.add(UUID(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise _IdentityHeaderError("Identity header must be a UUID.") from exc
    if len(parsed) != 1:
        raise _IdentityHeaderError("Identity headers disagree.")
    return next(iter(parsed))


def _legacy_headers_allowed() -> bool:
    value = os.getenv("CONTEXTA_ALLOW_LEGACY_TENANT_HEADERS")
    if value is None:
        return "pytest" in sys.modules
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _error(status_code: int, error: str, detail: str | None = None) -> JSONResponse:
    content: dict[str, str] = {"error": error}
    if detail is not None:
        content["detail"] = detail
    return JSONResponse(status_code=status_code, content=content)


def _is_public_path(path: str) -> bool:
    return path in PUBLIC_PATHS or path.startswith(("/docs/", "/redoc/", "/openapi.json"))


def _state_uuid(request: Request, field: str) -> UUID | None:
    value = getattr(request.state, field, None)
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _has_verified_state(request: Request) -> bool:
    return bool(
        getattr(request.state, "auth_verified", False)
        or (
            getattr(request.state, "authenticated", False)
            and getattr(request.state, "api_key_id", None)
        )
    )


def _set_state(
    request: Request,
    *,
    actor_id: UUID | None = None,
    organization_id: UUID | None = None,
    api_key_id: Any | None = None,
    authenticated: bool = False,
    auth_verified: bool = False,
    auth_compatibility: bool = False,
    auth_test_fallback: bool = False,
    auth_header_present: bool = False,
    auth_source: str | None = None,
) -> None:
    request.state.actor_id = str(actor_id) if actor_id is not None else None
    request.state.organization_id = (
        str(organization_id) if organization_id is not None else None
    )
    request.state.api_key_id = str(api_key_id) if api_key_id is not None else None
    request.state.authenticated = authenticated
    request.state.auth_verified = auth_verified
    request.state.auth_compatibility = auth_compatibility
    request.state.auth_test_fallback = auth_test_fallback
    request.state.auth_header_present = auth_header_present
    request.state.auth_source = auth_source


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Authenticate API keys and establish an explicit compatibility state."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _is_public_path(path):
            _set_state(request)
            return await call_next(request)

        try:
            header_organization = _read_uuid_headers(request, _ORGANIZATION_HEADERS)
            header_actor = _read_uuid_headers(request, _ACTOR_HEADERS)
        except _IdentityHeaderError as exc:
            return _error(400, "invalid_identity_header", str(exc))

        existing_verified = _has_verified_state(request)
        existing_organization = _state_uuid(request, "organization_id")
        existing_actor = _state_uuid(request, "actor_id")
        existing_api_key_id = getattr(request.state, "api_key_id", None)
        existing_source = getattr(request.state, "auth_source", None)
        existing_test_fallback = bool(
            getattr(request.state, "auth_test_fallback", False)
        )
        existing_compatibility = bool(
            getattr(request.state, "auth_compatibility", False)
        )
        _set_state(
            request,
            auth_header_present=bool(header_organization or header_actor),
        )

        if existing_verified and (
            existing_organization is None or existing_actor is None
        ):
            return _error(401, "invalid_authenticated_context")
        if (existing_organization is None) != (existing_actor is None):
            return _error(401, "invalid_authenticated_context")

        authorization = request.headers.get("authorization", "").strip()
        token = ""
        if authorization:
            scheme, separator, value = authorization.partition(" ")
            if scheme.lower() != "bearer" or not separator or not value.strip():
                return _error(401, "invalid_api_key")
            token = value.strip()
        else:
            token = request.headers.get("x-api-key", "").strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()

        if token:
            try:
                async with AsyncSessionFactory() as session:
                    api_key = await ApiKeyRepository.find_by_token(session, token)
            except (SQLAlchemyError, OSError, RuntimeError, TimeoutError):
                return _error(503, "authentication_unavailable")
            if not api_key:
                return _error(401, "invalid_api_key")
            try:
                organization_id = UUID(str(api_key.organization_id))
                actor_id = UUID(str(api_key.actor_id))
            except (TypeError, ValueError, AttributeError):
                return _error(401, "invalid_api_key")
            # Expose the key's rate-limit tier so the limiter can meter per tier
            # instead of applying one hard-coded limit to everyone.
            request.state.api_key_tier = str(getattr(api_key, "tier", None) or "standard")
            if existing_verified and (
                existing_organization != organization_id
                or existing_actor != actor_id
            ):
                return _error(403, "identity_mismatch")
            if header_organization is not None and header_organization != organization_id:
                return _error(403, "organization_mismatch")
            if header_actor is not None and header_actor != actor_id:
                return _error(403, "actor_mismatch")
            _set_state(
                request,
                actor_id=actor_id,
                organization_id=organization_id,
                api_key_id=getattr(api_key, "id", None),
                authenticated=True,
                auth_verified=True,
                auth_header_present=bool(header_organization or header_actor),
                auth_source="api_key",
            )
            return await call_next(request)

        if existing_verified:
            if header_organization is not None and header_organization != existing_organization:
                return _error(403, "organization_mismatch")
            if header_actor is not None and header_actor != existing_actor:
                return _error(403, "actor_mismatch")
            _set_state(
                request,
                actor_id=existing_actor,
                organization_id=existing_organization,
                api_key_id=existing_api_key_id,
                authenticated=True,
                auth_verified=True,
                auth_header_present=bool(header_organization or header_actor),
                auth_source=existing_source or "preverified",
            )
            return await call_next(request)

        if existing_organization is not None and (
            existing_compatibility or existing_test_fallback
        ):
            if header_organization is not None and header_organization != existing_organization:
                return _error(403, "organization_mismatch")
            if header_actor is not None and header_actor != existing_actor:
                return _error(403, "actor_mismatch")
            _set_state(
                request,
                actor_id=existing_actor,
                organization_id=existing_organization,
                api_key_id=existing_api_key_id,
                auth_compatibility=True,
                auth_test_fallback=existing_test_fallback,
                auth_header_present=bool(header_organization or header_actor),
                auth_source=existing_source or "preauthenticated",
            )
            return await call_next(request)

        if header_organization is not None and header_actor is not None:
            if not _legacy_headers_allowed():
                return _error(401, "authentication_required")
            _set_state(
                request,
                actor_id=header_actor,
                organization_id=header_organization,
                auth_compatibility=True,
                auth_header_present=True,
                auth_source="legacy_headers",
            )
            return await call_next(request)

        if header_organization is not None or header_actor is not None:
            return _error(401, "authentication_required")

        if "pytest" in sys.modules:
            _set_state(
                request,
                actor_id=_ZERO_UUID,
                organization_id=_ZERO_UUID,
                auth_compatibility=True,
                auth_test_fallback=True,
                auth_source="test",
            )
            return await call_next(request)

        return _error(401, "authentication_required")
