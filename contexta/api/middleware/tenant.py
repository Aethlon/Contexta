"""Tenant validation middleware."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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
_PUBLIC_PATHS = {
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


class _TenantValueError(ValueError):
    pass


def _as_uuid(value: Any, field: str) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise _TenantValueError(f"{field} must be a UUID.") from exc


def _header_uuid(request: Request, names: tuple[str, ...], field: str) -> UUID | None:
    values = {
        value.strip()
        for name in names
        for value in request.headers.getlist(name)
        if value and value.strip()
    }
    if not values:
        return None
    parsed = {_as_uuid(value, field) for value in values}
    if len(parsed) != 1:
        raise _TenantValueError(f"{field} headers disagree.")
    return next(iter(parsed))


def _query_uuid(request: Request, names: tuple[str, ...], field: str) -> UUID | None:
    values = {
        value.strip()
        for name in names
        for value in request.query_params.getlist(name)
        if value and value.strip()
    }
    if not values:
        return None
    parsed = {_as_uuid(value, field) for value in values}
    if len(parsed) != 1:
        raise _TenantValueError(f"{field} query parameters disagree.")
    return next(iter(parsed))


def _forbidden(detail: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": detail})


def _unauthorized(detail: str) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": detail})


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(
        ("/docs/", "/redoc/", "/openapi.json")
    )


class TenantMiddleware(BaseHTTPMiddleware):
    """Reject invalid or conflicting tenant and actor context."""

    async def dispatch(self, request: Request, call_next):
        if _is_public_path(request.url.path):
            return await call_next(request)

        try:
            state_org = _as_uuid(
                getattr(request.state, "organization_id", None),
                "organization_id",
            )
            state_actor = _as_uuid(
                getattr(request.state, "actor_id", None),
                "actor_id",
            )
            header_org = _header_uuid(request, _ORGANIZATION_HEADERS, "organization_id")
            header_actor = _header_uuid(request, _ACTOR_HEADERS, "actor_id")
            query_org = _query_uuid(request, ("organization_id",), "organization_id")
            query_actor = _query_uuid(
                request,
                ("user_id", "actor_id"),
                "actor_id",
            )
        except _TenantValueError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": str(exc)},
            )

        test_fallback = bool(getattr(request.state, "auth_test_fallback", False))
        if test_fallback and header_org is None and header_actor is None:
            return await call_next(request)

        if getattr(request.state, "auth_verified", False) and (
            state_org is None or state_actor is None
        ):
            return _unauthorized("Authenticated tenant context is invalid.")

        if (state_org is None) != (state_actor is None):
            return _unauthorized("Authenticated tenant context is incomplete.")

        if state_org is None:
            if header_org is not None and query_org is not None and header_org != query_org:
                return _forbidden("Request organization_id does not match the organization header.")
            if header_actor is not None and query_actor is not None and header_actor != query_actor:
                return _forbidden("Request user_id does not match the actor header.")
            if (
                header_org is not None
                or header_actor is not None
                or query_org is not None
                or query_actor is not None
            ):
                return _unauthorized("Authentication required.")
            return await call_next(request)

        if header_org is not None and header_org != state_org:
            return _forbidden("Authenticated tenant does not match request organization_id.")
        if query_org is not None and query_org != state_org:
            return _forbidden("Authenticated tenant does not match request organization_id.")
        if header_actor is not None and header_actor != state_actor:
            return _forbidden("Authenticated actor does not match request user identity.")
        if query_actor is not None and query_actor != state_actor:
            return _forbidden("Authenticated actor does not match request user_id.")

        return await call_next(request)
