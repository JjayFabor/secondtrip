"""App factory. See docs/architecture/01-system-architecture.md §3.1 for
the middleware order this wires, and 18-observability.md §6 for the two
health endpoints.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware

from app.api.middleware.csrf import CSRFMiddleware
from app.api.middleware.logging import LoggingMiddleware
from app.api.middleware.request_id import RequestIdMiddleware
from app.api.middleware.security_headers import SecurityHeadersMiddleware
from app.api.v1.router import api_v1_router
from app.composition import AppState, build_app_state
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.openapi import stable_operation_id
from app.core.settings import get_settings
from app.modules.detection.service import assert_signal_catalogue

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    state = build_app_state(settings)
    app.state.app_state = state
    async with state.session_factory() as session, session.begin():
        await assert_signal_catalogue(session)
    if settings.worker_enabled:
        state.worker.start()
    log.info("app.startup", app_env=settings.app_env)
    try:
        yield
    finally:
        if settings.worker_enabled:
            await state.worker.stop()
        await state.engine.dispose()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        generate_unique_id_function=stable_operation_id,
    )

    # Middleware order (innermost to outermost, since Starlette wraps
    # each add_middleware call around the previous stack): CORS, CSRF,
    # security headers, access logging, request-id. Request-id is outermost
    # so every other layer (and every log line) can rely on it already being
    # bound.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id"],
        max_age=600,
    )
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=settings.cors_allowed_origins,
        csrf_cookie_name=settings.csrf_cookie_name,
        cookie_domain=settings.cookie_domain,
        cookie_secure=settings.cookie_secure,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)
    app.include_router(api_v1_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        # No database call — see 18-observability.md §6. A health check that
        # fails during a brief reconnect must not cause a platform restart.
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        state: AppState = app.state.app_state
        async with state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await state.storage_provider.head("__secondtrip_readiness__")
        return {"status": "ok"}

    return app


app = create_app()
