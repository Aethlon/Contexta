"""Tenant validation middleware."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class TenantMiddleware(BaseHTTPMiddleware):
    """Reject obvious cross-tenant requests when tenant headers and query differ."""

    async def dispatch(self, request: Request, call_next):
        header_org = request.headers.get("x-organization-id")
        query_org = request.query_params.get("organization_id")
        if header_org and query_org and header_org != query_org:
            return JSONResponse(
                status_code=403,
                content={"detail": "Authenticated tenant does not match request organization_id."},
            )
        return await call_next(request)
