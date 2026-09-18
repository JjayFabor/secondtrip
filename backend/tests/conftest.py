from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.settings import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture
async def owner_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Connects as the table-owning migration role — used only to arrange
    test fixtures (inserting rows across tenants), never to exercise the
    behavior under test."""
    engine = create_async_engine(settings.database_url_migrations)
    yield engine
    await engine.dispose()


@pytest.fixture
async def app_engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    """Connects as secondtrip_app — the non-owner, RLS-bound role the
    application always uses. This is the role under test."""
    engine = create_async_engine(settings.database_url, connect_args={"statement_cache_size": 0})
    yield engine
    await engine.dispose()


async def set_org_context(session: AsyncSession, organization_id: UUID) -> None:
    """Mirrors app.db.session.tenant_session's use of set_config — see
    that module's docstring for why set_config rather than a literal
    SET LOCAL string.

    Deliberately takes no "clear the context" mode: to test the unset
    case, use a session that never calls this at all. Passing NULL through
    set_config produces an empty string, not SQL NULL — see
    migrations/rls_helpers.py — so a helper that accepted `None` here
    would invite exactly the bug that function's NULLIF guards against.
    """
    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(organization_id)},
    )
