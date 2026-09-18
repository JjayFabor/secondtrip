"""The app role's own attributes — independent of any table's RLS policy.
See docs/architecture/02-multi-tenancy.md §2 and CLAUDE.md rule 4.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_app_role_has_no_bypassrls(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT rolbypassrls, rolsuper FROM pg_roles WHERE rolname = 'secondtrip_app'")
        )
        row = result.one()

    assert row.rolbypassrls is False, "secondtrip_app must never have BYPASSRLS"
    assert row.rolsuper is False, "secondtrip_app must never be a superuser"


async def test_app_role_does_not_own_the_smoke_test_table(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tableowner FROM pg_tables WHERE tablename = '_rls_smoke_test'")
        )
        owner = result.scalar_one()

    assert owner != "secondtrip_app", (
        "if secondtrip_app owned this table, FORCE ROW LEVEL SECURITY would not apply to "
        "it — an owner bypasses its own table's RLS policies by default"
    )
