"""Access logging middleware — see docs/architecture/18-observability.md §2, §3."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import redact_request_path

log = structlog.get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        event = "http.request.slow" if duration_ms > 1000 else "http.request"
        log.info(
            event,
            method=request.method,
            path=redact_request_path(request.url.path),
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
