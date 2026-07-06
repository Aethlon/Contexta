"""FastAPI application entry point for the contexta API."""

from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from contexta.api.middleware.auth import AuthenticationMiddleware
from contexta.api.middleware.tenant import TenantMiddleware
from contexta.api.middleware.logging import RequestLoggingMiddleware
from contexta.api.routes.api_keys import router as api_keys_router
from contexta.api.routes.memories import router as memories_router
from contexta.api.routes.observations import router as observations_router
from contexta.api.routes.retrieval import router as retrieval_router
from contexta.api.routes.graph import router as graph_router
from contexta.api.routes.sessions import router as sessions_router
from contexta.api.routes.auth import router as auth_router
from contexta.api.routes.billing import router as billing_router
from contexta.config.logging import setup_logging
from contexta.config.settings import get_settings
from contexta.db import check_db, check_redis

settings = get_settings()

# Setup structured JSON logging
setup_logging()

# Initialize Sentry if DSN is provided
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastAPIIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastAPIIntegration()],
        traces_sample_rate=1.0,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    import sys
    is_testing = "pytest" in sys.modules
    if settings.db_boot_check and not is_testing:
        db_ok = await check_db()
        if not db_ok:
            raise RuntimeError("Database boot check failed! Could not connect to Postgres database.")
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="contexta Memory Intelligence Engine",
        description="Memory intelligence pipeline for AI agents.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Store settings on app state for route access
    app.state.settings = settings

    # Middleware execution order: Request Logging (outermost) -> CORS/GZip -> Auth -> Tenant
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(AuthenticationMiddleware)

    # Configure Prometheus metrics instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Public health check endpoints
    @app.get("/healthz", status_code=status.HTTP_200_OK, tags=["system"])
    async def healthz() -> dict:
        """Lightweight endpoint to verify service is running."""
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/readyz", tags=["system"])
    async def readyz() -> JSONResponse:
        """Deep check validating connectivity to Postgres and Redis."""
        db_ok = await check_db()
        redis_ok = await check_redis()
        status_code = status.HTTP_200_OK if db_ok and redis_ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={
                "db": "ok" if db_ok else "failed",
                "redis": "ok" if redis_ok else "failed",
            },
        )

    # Include routes
    app.include_router(api_keys_router)
    app.include_router(observations_router, prefix="/v1/observations", tags=["observations"])
    app.include_router(retrieval_router, prefix="/v1", tags=["retrieval"])
    app.include_router(memories_router, prefix="/v1/memories", tags=["memories"])
    app.include_router(graph_router, prefix="/v1/entities", tags=["entities"])
    app.include_router(sessions_router, prefix="/v1/sessions", tags=["sessions"])
    app.include_router(auth_router)
    app.include_router(billing_router)

    return app


app = create_app()
