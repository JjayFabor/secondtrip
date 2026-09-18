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

from app.api.middleware.logging import LoggingMiddleware
from app.api.middleware.request_id import RequestIdMiddleware
from app.composition import AppState, build_app_state
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.settings import get_settings

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    state = build_app_state(settings)
    app.state.app_state = state
    log.info("app.startup", app_env=settings.app_env)
    yield
    await state.engine.dispose()
    log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-Id", "Idempotency-Key"],
        expose_headers=["X-Request-Id"],
        max_age=600,
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    register_error_handlers(app)

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
        return {"status": "ok"}

    return app


app = create_app()
