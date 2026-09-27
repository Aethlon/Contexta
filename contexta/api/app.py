"""FastAPI application entry point for the contexta API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator

from contexta.api.middleware.auth import AuthenticationMiddleware
from contexta.api.middleware.logging import RequestLoggingMiddleware
from contexta.api.middleware.ratelimit import RateLimitMiddleware
from contexta.api.middleware.response_cache import ResponseCacheMiddleware
from contexta.api.middleware.tenant import TenantMiddleware
from contexta.api.routes.api_keys import router as api_keys_router
from contexta.api.routes.artifacts import router as artifacts_router
from contexta.api.routes.audit import router as audit_router
from contexta.api.routes.auth import router as auth_router
from contexta.api.routes.graph import router as graph_router
from contexta.api.routes.kernel_runtime import router as kernel_runtime_router
from contexta.api.routes.memories import router as memories_router
from contexta.api.routes.memory_kernel import router as memory_kernel_router
from contexta.api.routes.observations import router as observations_router
from contexta.api.routes.retrieval import router as retrieval_router
from contexta.api.routes.sessions import router as sessions_router
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
    if not is_testing:
        db_ok = await check_db()
        if not db_ok:
            import structlog
            structlog.get_logger("contexta.engine").warning(
                "database_offline",
                msg="Database is not reachable. Operating in standalone mode without active database persistence.",
            )
    if (
        settings.validate_online_providers_at_startup
        and settings.engine_mode == "online"
        and (not settings.llm_api_key or not settings.embedding_api_key)
    ):
        import structlog
        log = structlog.get_logger("contexta.engine")
        log.warning(
            "online_mode_dual_provider_warning",
            msg="Online mode requires BOTH LLM and Embedding provider API keys. Automatically falling back unconfigured provider to local model server.",
            has_llm=bool(settings.llm_api_key),
            has_embedding=bool(settings.embedding_api_key),
        )
    yield



def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="contexta Memory Intelligence Engine",
        description="Memory intelligence pipeline for AI agents.",
        version="1.5.0",
        lifespan=lifespan,
    )

    # Store settings on app state for route access
    app.state.settings = settings

    # Middleware is executed last-added-first, so the effective request order is:
    #   Authentication -> Tenant -> ResponseCache -> RateLimit -> GZip -> CORS -> logging
    # The cache and limiter sit inside auth/tenant because they need the resolved
    # organization, actor and API key, and outside GZip so a cached entry replays
    # with its content-encoding intact. The cache is outside the limiter on
    # purpose: a served-from-cache read should not consume the caller's quota.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(ResponseCacheMiddleware)
    app.add_middleware(TenantMiddleware)
    app.add_middleware(AuthenticationMiddleware)

    # Configure Prometheus metrics instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    # Public health check endpoints
    @app.get("/healthz", status_code=status.HTTP_200_OK, tags=["system"])
    async def healthz() -> dict:
        """Lightweight endpoint to verify service is running."""
        return {"status": "ok", "version": "1.5.0"}

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
    from contexta.api.routes.system import router as system_router

    app.include_router(system_router, prefix="/v1")
    app.include_router(system_router)
    app.include_router(api_keys_router)
    app.include_router(artifacts_router, prefix="/v1/artifacts", tags=["artifacts"])
    app.include_router(audit_router)
    # NOTE: audit_router already carries its own "/v1/audit" prefix. Mounting it
    # again under prefix="/audit" produced a doubled, unreachable "/audit/v1/audit"
    # path in the OpenAPI schema, so it is intentionally mounted only once.
    app.include_router(observations_router, prefix="/v1/observations", tags=["observations"])
    app.include_router(retrieval_router, prefix="/v1", tags=["retrieval"])
    app.include_router(retrieval_router, tags=["retrieval"])
    app.include_router(memories_router, prefix="/v1/memories", tags=["memories"])
    app.include_router(memories_router, prefix="/memories", tags=["memories"])
    app.include_router(memory_kernel_router, prefix="/v1/memory-kernel", tags=["memory-kernel"])
    app.include_router(kernel_runtime_router, prefix="/v1/kernel", tags=["kernel-runtime"])
    app.include_router(graph_router, prefix="/v1/entities", tags=["entities"])
    app.include_router(graph_router, prefix="/v1/graph", tags=["graph"])
    app.include_router(graph_router, prefix="/graph", tags=["graph"])
    app.include_router(sessions_router, prefix="/v1/sessions", tags=["sessions"])
    app.include_router(auth_router)

    return app


app = create_app()
