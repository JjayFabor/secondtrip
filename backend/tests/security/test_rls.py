"""RLS proof — see docs/architecture/21-implementation-sequencing.md Phase 2
exit criteria and CLAUDE.md's "tests that must never be weakened" list.

Exercises raw SQL through the actual secondtrip_app role, not the ORM and
not a mocked connection — this is what makes it a proof of the database
mechanism rather than a proof of Python code that assumes the mechanism
works.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

TABLE = "_rls_smoke_test"


@pytest.fixture(autouse=True)
async def _clean_table(owner_engine: AsyncEngine) -> AsyncIterator[None]:
    async with owner_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLE}"))
    yield


async def _seed_two_tenants(owner_engine: AsyncEngine) -> tuple[UUID, UUID]:
    org_a, org_b = uuid4(), uuid4()
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(f"INSERT INTO {TABLE} (organization_id, label) VALUES (:org, 'a-row')"),
            {"org": str(org_a)},
        )
        await conn.execute(
            text(f"INSERT INTO {TABLE} (organization_id, label) VALUES (:org, 'b-row')"),
            {"org": str(org_b)},
        )
    return org_a, org_b


async def test_app_role_only_sees_its_own_tenant(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, _org_b = await _seed_two_tenants(owner_engine)

    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_a)}
        )
        rows = (await conn.execute(text(f"SELECT label FROM {TABLE}"))).scalars().all()

    assert rows == ["a-row"], "org A's session must see only org A's row, never org B's"


async def test_app_role_cannot_write_into_another_tenant(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    org_a, org_b = await _seed_two_tenants(owner_engine)

    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"), {"org": str(org_a)}
        )
        try:
            await conn.execute(
                text(f"INSERT INTO {TABLE} (organization_id, label) VALUES (:org, 'forged')"),
                {"org": str(org_b)},
            )
            await conn.commit()
            forged_inserted = True
        except DBAPIError:
            forged_inserted = False

    assert not forged_inserted, (
        "WITH CHECK must reject a row whose organization_id doesn't match the session's "
        "context, even though the app role otherwise has INSERT privilege on the table"
    )


async def test_missing_tenant_context_returns_zero_rows_not_an_error(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """The context was never set on this connection at all — the
    `missing_ok=true` argument to current_setting is what's under test
    here, distinct from the NULLIF case below."""
    await _seed_two_tenants(owner_engine)

    async with app_engine.connect() as conn:
        rows = (await conn.execute(text(f"SELECT label FROM {TABLE}"))).scalars().all()

    assert rows == [], "a query with no tenant context set must return empty, never raise"


async def test_explicitly_cleared_context_also_returns_zero_rows_not_an_error(
    owner_engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    """Regression test for the NULLIF fix in migrations/rls_helpers.py:
    set_config(key, NULL, true) produces an empty string, not SQL NULL,
    and ''::uuid raises unless the policy guards against it. Verified to
    fail loudly (DBAPIError) before that fix was applied."""
    await _seed_two_tenants(owner_engine)

    async with app_engine.connect() as conn, conn.begin():
        await conn.execute(text("SELECT set_config('app.current_org_id', NULL, true)"))
        rows = (await conn.execute(text(f"SELECT label FROM {TABLE}"))).scalars().all()

    assert rows == [], "an explicitly-cleared context must also degrade to zero rows"


async def test_owner_role_bypasses_rls_which_is_exactly_why_the_app_never_uses_it(
    owner_engine: AsyncEngine,
) -> None:
    """Documents the property that makes 'app connects as a non-owner
    role' a load-bearing requirement rather than a style preference: the
    owner sees everything regardless of context, by Postgres default."""
    await _seed_two_tenants(owner_engine)

    async with owner_engine.connect() as conn:
        rows = (await conn.execute(text(f"SELECT label FROM {TABLE}"))).scalars().all()

    assert set(rows) == {"a-row", "b-row"}
