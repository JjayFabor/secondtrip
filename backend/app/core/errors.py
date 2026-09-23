"""Domain exceptions and RFC 9457 (`application/problem+json`) responses.

See docs/architecture/15-api-design.md §1. `code` is the stable machine
identifier the frontend switches on; `detail` is the human sentence.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger(__name__)

_PROBLEM_BASE = "https://secondtrip.dev/errors"


class ApplicationError(Exception):
    """Base for every domain exception. Routers never construct one of
    these directly with ad-hoc fields — subclass it."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "APPLICATION_ERROR"
    title: str = "Application error"

    def __init__(self, detail: str, *, errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors or []


class NotFoundError(ApplicationError):
    """A missing row AND a wrong-tenant row both raise this — see
    CLAUDE.md rule 3. Never a 403 for a cross-tenant lookup."""

    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    title = "Not found"


class UnauthorizedError(ApplicationError):
    """Missing, invalid, or expired session — see
    docs/architecture/03-authentication.md §2."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    title = "Authentication required"


class ForbiddenError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    title = "Forbidden"


class ConflictError(ApplicationError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    title = "Conflict"


class RateLimitExceededError(ApplicationError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "RATE_LIMITED"
    title = "Too many requests"

    def __init__(self, detail: str, *, retry_after: int) -> None:
        super().__init__(detail)
        self.retry_after = retry_after


class ServiceUnavailableError(ApplicationError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "SERVICE_UNAVAILABLE"
    title = "Service unavailable"


class InvalidCursorRequestError(ApplicationError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_CURSOR"
    title = "Invalid cursor"


class EntitlementExceededError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ENTITLEMENT_EXCEEDED"
    title = "Entitlement exceeded"


def _problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    title: str,
    detail: str,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body: dict[str, object] = {
        "type": f"{_PROBLEM_BASE}/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "request_id": request_id,
    }
    if errors:
        body["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def _application_error_handler(request: Request, exc: ApplicationError) -> JSONResponse:
        headers: dict[str, str] | None = None
        if isinstance(exc, RateLimitExceededError):
            headers = {"Retry-After": str(exc.retry_after)}
        return _problem_response(
            request,
            status_code=exc.status_code,
            code=exc.code,
            title=exc.title,
            detail=exc.detail,
            errors=exc.errors,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {
                "field": ".".join(str(loc) for loc in e["loc"] if loc != "body"),
                "code": e["type"].upper(),
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return _problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            title="Validation failed",
            detail="One or more fields failed validation.",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _problem_response(
            request,
            status_code=exc.status_code,
            code="HTTP_ERROR",
            title="HTTP error",
            detail=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.error("unhandled_exception", exc_info=exc, request_id=request_id)
        return _problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="INTERNAL_ERROR",
            title="Internal server error",
            detail="An unexpected error occurred. Reference the request ID when reporting this.",
        )
