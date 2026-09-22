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


async def test_app_role_does_not_own_tenant_tables(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT tablename, tableowner "
                "FROM pg_tables "
                "WHERE tablename IN "
                "('organization_memberships', 'organization_invitations', 'audit_events') "
                "ORDER BY tablename"
            )
        )
        rows = result.all()

    assert {row.tablename for row in rows} == {
        "audit_events",
        "organization_invitations",
        "organization_memberships",
    }
    assert all(row.tableowner != "secondtrip_app" for row in rows), (
        "if secondtrip_app owned a tenant table, FORCE ROW LEVEL SECURITY would not apply "
        "to it — an owner bypasses its own table's RLS policies by default"
    )


async def test_audit_events_are_append_only_for_app_role(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT has_table_privilege('secondtrip_app', 'audit_events', 'SELECT'), "
                "       has_table_privilege('secondtrip_app', 'audit_events', 'INSERT'), "
                "       has_table_privilege('secondtrip_app', 'audit_events', 'UPDATE'), "
                "       has_table_privilege('secondtrip_app', 'audit_events', 'DELETE')"
            )
        )
        select_privilege, insert_privilege, update_privilege, delete_privilege = result.one()

    assert select_privilege is True
    assert insert_privilege is True
    assert update_privilege is False
    assert delete_privilege is False
