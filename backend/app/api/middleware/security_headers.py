"""Response security posture shared by the API and browser-facing clients."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Set headers that must not be left to individual route authors."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), geolocation=(), microphone=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )

        # Tenant responses contain customer data and must never be stored by a
        # shared browser or intermediary. Include the collection endpoint as
        # well as /orgs/{id}/... because it also returns private membership data.
        if request.url.path == "/api/v1/orgs" or request.url.path.startswith("/api/v1/orgs/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response
