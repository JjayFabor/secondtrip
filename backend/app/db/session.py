"""Session factories — see docs/architecture/02-multi-tenancy.md §2 and
CLAUDE.md rule 4.

Three shapes, because not every authenticated request is org-scoped:

- `tenant_session` — the normal case. Sets BOTH `app.current_org_id` and
  `app.current_user_id`. Used by every `/orgs/{org_id}/*` route.
- `user_session` — for routes that act on behalf of a user but are not
  scoped to one organization (`GET /me`, `GET /orgs` — "list my orgs").
  Sets only `app.current_user_id`. `organization_memberships`' RLS
  policy has a second clause (`OR user_id = current_setting(
  'app.current_user_id', true)`) specifically so this case can list a
  user's own memberships across every org without bypassing RLS or
  needing a per-org context that doesn't exist yet for this request.
- `token_lookup_session` — the narrow exception, for resolving an
  organization_invitations row by its bearer token before the caller has
  any membership (or even necessarily an account) in that org.
  `organization_invitations`' RLS policy has a matching second clause
  (`OR token_hash = current_setting('app.lookup_token_hash', true)`).
  Possession of the raw token (32 bytes from secrets.token_urlsafe,
  256 bits of entropy) is the authorization for this one lookup — the
  same trust model session tokens themselves use, just expressed as an
  RLS clause instead of a table with no RLS at all, because this table
  otherwise needs standard org-scoped protection for its list/manage
  operations.

All three use `set_config(..., true)`, never a literal `SET LOCAL '...'`
string — see the module's original docstring reasoning, preserved below.

`set_config()` is used instead of a literal `SET LOCAL app.current_org_id
= '...'` string because `set_config` is a normal parameterized function
call — the safe way to pass a value into a GUC. `SET` does not accept bind
parameters at all, which is what makes the string-interpolation version an
avoidable injection surface even though the value is a UUID we control.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.tenancy import TenantContext


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession], tenant: TenantContext
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, session.begin():
        await session.execute(
            text(
                "SELECT set_config('app.current_org_id', :org_id, true), "
                "set_config('app.current_user_id', :user_id, true)"
            ),
            {
                "org_id": str(tenant.organization_id),
                "user_id": str(tenant.actor_user_id) if tenant.actor_user_id else None,
            },
        )
        yield session


@asynccontextmanager
async def user_session(
    session_factory: async_sessionmaker[AsyncSession], user_id: UUID
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_user_id', :user_id, true)"),
            {"user_id": str(user_id)},
        )
        yield session


@asynccontextmanager
async def token_lookup_session(
    session_factory: async_sessionmaker[AsyncSession], token_hash: str
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.lookup_token_hash', :hash, true)"),
            {"hash": token_hash},
        )
        yield session


@asynccontextmanager
async def worker_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Cross-tenant queue maintenance context used only by the worker.

    A claimed tenant job is executed in a fresh ``tenant_session``; this
    context exists only for claiming/heartbeating/state transitions that must
    inspect the queue before an organization is known.
    """
    async with session_factory() as session, session.begin():
        await session.execute(text("SELECT set_config('app.worker_context', '1', true)"))
        yield session
