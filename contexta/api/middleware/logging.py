"""Request logging and request ID injection middleware."""

from __future__ import annotations

import time
import uuid
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to inject Request IDs and log request execution statistics as JSON."""

    async def dispatch(self, request: Request, call_next):
        # Retrieve or generate Request ID
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())

        # Bind request_id to structlog contextvars for automatic attachment to downstream logs
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception as exc:
            # Log unexpected exceptions with request context before re-raising
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                path=request.url.path,
                method=request.method,
                status_code=500,
                duration_ms=round(duration_ms, 2),
                error=str(exc),
                exc_info=True,
            )
            raise exc

        # Calculate elapsed duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Attach request_id to response headers
        response.headers["x-request-id"] = request_id

        # Log completion details
        logger.info(
            "request_processed",
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        return response
