"""Identity's dependency helpers — everything about "who is the
caller", as opposed to organizations/deps.py's "which org, what role".

Lives inside the identity module rather than a shared app/api/deps.py:
these functions need IdentityRepository/resolve_session, and "modules
never import api" means api-layer code can't own something modules
depend on. Other modules' routers import this the same way they'd
import any other module's service — see
docs/architecture/01-system-architecture.md §5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.errors import UnauthorizedError
from app.core.security import hash_ip
from app.db.session import user_session
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.service import resolve_session


def get_client_ip_hash(
    request: Request, app_state: AppState = Depends(get_app_state)
) -> str | None:
    if request.client is None:
        return None
    return hash_ip(request.client.host, app_secret=app_state.settings.app_secret)


@dataclass(frozen=True, slots=True)
class AuthenticatedUser:
    """A plain view of the session's principal — never the ORM `User`
    object, which would be detached from its session by the time a
    router uses it. Extracted inside `require_session` before that
    session closes."""

    session_id: UUID
    id: UUID
    email: str
    full_name: str
    status: str


async def require_session(
    request: Request, app_state: AppState = Depends(get_app_state)
) -> AuthenticatedUser:
    raw_token = request.cookies.get(app_state.settings.session_cookie_name)
    if not raw_token:
        raise UnauthorizedError("Sign in required.")

    async with app_state.session_factory() as session, session.begin():
        repo = IdentityRepository(session)
        result = await resolve_session(repo, app_state.settings, raw_token=raw_token)
        if result is None:
            raise UnauthorizedError("Your session has expired. Sign in again.")
        return AuthenticatedUser(
            session_id=result.session.id,
            id=result.user.id,
            email=result.user.email,
            full_name=result.user.full_name,
            status=result.user.status,
        )


async def get_user_scoped_session(
    user: AuthenticatedUser = Depends(require_session),
    app_state: AppState = Depends(get_app_state),
) -> AsyncIterator[AsyncSession]:
    """For routes that act on behalf of a user but aren't scoped to one
    organization — `GET /orgs`, `GET /me` — see db/session.py's
    module docstring."""
    async with user_session(app_state.session_factory, user.id) as session:
        yield session
