"""Tenant-aware session factory.

See docs/architecture/02-multi-tenancy.md §2 and CLAUDE.md rule 4. Every
session opened through `tenant_session` sets `app.current_org_id` as the
FIRST statement of the transaction via `set_config(..., true)` — the
`true` third argument makes it transaction-local, exactly like `SET
LOCAL`, which is what makes this safe under PgBouncer transaction pooling
(the setting cannot leak to the next tenant that borrows the connection).

`set_config()` is used instead of a literal `SET LOCAL app.current_org_id
= '...'` string because `set_config` is a normal parameterized function
call — the safe way to pass a value into a GUC. `SET` does not accept bind
parameters at all, which is what makes the string-interpolation version an
avoidable injection surface even though the value is a UUID we control.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.tenancy import TenantContext


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession], tenant: TenantContext
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(tenant.organization_id)},
        )
        yield session
