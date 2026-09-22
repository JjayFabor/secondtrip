from fastapi import status

from app.core.errors import ApplicationError


class InvalidCredentialsError(ApplicationError):
    """Deliberately the SAME error for 'no such user' and 'wrong
    password' — see docs/architecture/03-authentication.md §3."""

    status_code = status.HTTP_401_UNAUTHORIZED
    code = "INVALID_CREDENTIALS"
    title = "Invalid credentials"


class AccountLockedError(ApplicationError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "ACCOUNT_LOCKED"
    title = "Account temporarily locked"


class InvalidTokenError(ApplicationError):
    """Covers expired, already-consumed, and simply-not-found tokens —
    one error, so a client can't distinguish "guessed wrong" from
    "guessed right but late", which is the point."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "INVALID_TOKEN"
    title = "This link is invalid or has expired"


class AccountNotVerifiedError(ApplicationError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "ACCOUNT_NOT_VERIFIED"
    title = "Email not verified"
