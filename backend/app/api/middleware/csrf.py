"""CSRF protection — see docs/architecture/03-authentication.md §5.

Two independent checks for every state-changing request (anything but
GET/HEAD/OPTIONS): the Origin header must match an allowed origin, and
the double-submit cookie must match the X-CSRF-Token header. Either
failing is a 403. SameSite=Lax on the session cookie is the first line
of defense (it already blocks cross-site form posts); this middleware
covers the rest — browsers or contexts where SameSite behaves
unexpectedly, and direct API calls from the browser that bypass the
Next.js server-side proxy.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PATHS = frozenset({"/health", "/ready"})
_EXEMPT_PREFIXES = ("/api/v1/storage/local/",)


class CSRFMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_origins: list[str],
        csrf_cookie_name: str,
        cookie_secure: bool,
    ) -> None:
        super().__init__(app)
        self._allowed_origins = set(allowed_origins)
        self._csrf_cookie_name = csrf_cookie_name
        self._cookie_secure = cookie_secure

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            request.method in _SAFE_METHODS
            or request.url.path in _EXEMPT_PATHS
            or request.url.path.startswith(_EXEMPT_PREFIXES)
        ):
            return await self._ensure_csrf_cookie(request, await call_next(request))

        origin = request.headers.get("origin")
        if origin is None or origin not in self._allowed_origins:
            return JSONResponse(
                status_code=403,
                content={
                    "type": "https://secondtrip.dev/errors/forbidden",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Request origin not allowed.",
                    "code": "CSRF_ORIGIN_MISMATCH",
                },
                media_type="application/problem+json",
            )

        cookie_token = request.cookies.get(self._csrf_cookie_name)
        header_token = request.headers.get("x-csrf-token")
        if not cookie_token or not header_token or cookie_token != header_token:
            return JSONResponse(
                status_code=403,
                content={
                    "type": "https://secondtrip.dev/errors/forbidden",
                    "title": "Forbidden",
                    "status": 403,
                    "detail": "Missing or invalid CSRF token.",
                    "code": "CSRF_TOKEN_MISMATCH",
                },
                media_type="application/problem+json",
            )

        return await self._ensure_csrf_cookie(request, await call_next(request))

    async def _ensure_csrf_cookie(self, request: Request, response: Response) -> Response:
        """Issue the double-submit cookie on any response that doesn't
        already carry one — deliberately NOT httpOnly, so client-side JS
        can read it and echo it back as X-CSRF-Token."""
        if self._csrf_cookie_name not in request.cookies:
            response.set_cookie(
                self._csrf_cookie_name,
                secrets.token_urlsafe(32),
                secure=self._cookie_secure,
                samesite="lax",
                httponly=False,
                path="/",
            )
        return response
