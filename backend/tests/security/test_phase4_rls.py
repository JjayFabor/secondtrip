from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.modules.billing.entitlements.keys import EntitlementKey

TENANT_TABLES = {
    "api_idempotency_records",
    "background_jobs",
    "billing_events",
    "customers",
    "equipment",
    "import_batches",
    "import_column_mappings",
    "import_rows",
    "job_line_items",
    "job_notes",
    "jobs",
    "locations",
    "organization_entitlement_overrides",
    "organization_subscriptions",
    "service_categories",
    "source_systems",
    "technicians",
    "usage_counters",
}


async def test_every_phase4_tenant_table_has_forced_rls(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:table_names)"
                ),
                {"table_names": sorted(TENANT_TABLES)},
            )
        ).all()
    assert {row.relname for row in rows} == TENANT_TABLES
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)


async def test_phase4_tables_are_not_owned_by_app_role(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE tablename = ANY(:table_names)"
                ),
                {"table_names": sorted(TENANT_TABLES)},
            )
        ).all()
    assert {row.tablename for row in rows} == TENANT_TABLES
    assert all(row.tableowner != "secondtrip_app" for row in rows)


async def test_all_documented_plan_entitlements_are_seeded(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        count = (
            await connection.execute(text("SELECT count(*) FROM plan_entitlements"))
        ).scalar_one()
        plans = (
            (await connection.execute(text("SELECT key FROM plans ORDER BY sort_order")))
            .scalars()
            .all()
        )
    assert plans == ["free", "pro", "business"]
    assert count == len(EntitlementKey) * len(plans)


async def test_nullable_parent_reference_is_tenant_safe_and_still_sets_null(
    owner_engine: AsyncEngine,
) -> None:
    user_id, org_a, org_b = uuid4(), uuid4(), uuid4()
    parent_id, child_id = uuid4(), uuid4()
    async with owner_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                text(
                    "INSERT INTO users (id, email, full_name, status) "
                    "VALUES (:id, :email, 'FK Test', 'active')"
                ),
                {"id": user_id, "email": f"fk-{user_id}@example.test"},
            )
            await connection.execute(
                text(
                    "INSERT INTO organizations (id, name, slug) VALUES "
                    "(:org_a, 'FK A', :slug_a), (:org_b, 'FK B', :slug_b)"
                ),
                {
                    "org_a": org_a,
                    "org_b": org_b,
                    "slug_a": f"fk-a-{org_a}",
                    "slug_b": f"fk-b-{org_b}",
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO organization_memberships (organization_id, user_id, role) "
                    "VALUES (:org_a, :user_id, 'owner'), (:org_b, :user_id, 'owner')"
                ),
                {"org_a": org_a, "org_b": org_b, "user_id": user_id},
            )
            await connection.execute(
                text(
                    "INSERT INTO service_categories "
                    "(id, organization_id, key, label) VALUES "
                    "(:parent_id, :org_a, 'parent', 'Parent'), "
                    "(:child_id, :org_a, 'child', 'Child')"
                ),
                {
                    "parent_id": parent_id,
                    "child_id": child_id,
                    "org_a": org_a,
                },
            )
            await connection.execute(
                text("UPDATE service_categories SET parent_id = :parent WHERE id = :child"),
                {"parent": parent_id, "child": child_id},
            )
            await connection.execute(
                text("DELETE FROM service_categories WHERE id = :parent"),
                {"parent": parent_id},
            )
            assert (
                await connection.execute(
                    text("SELECT parent_id FROM service_categories WHERE id = :child"),
                    {"child": child_id},
                )
            ).scalar_one() is None

            other_parent = uuid4()
            await connection.execute(
                text(
                    "INSERT INTO service_categories "
                    "(id, organization_id, key, label) "
                    "VALUES (:id, :org_b, 'other-parent', 'Other Parent')"
                ),
                {"id": other_parent, "org_b": org_b},
            )
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("UPDATE service_categories SET parent_id = :parent WHERE id = :child"),
                    {"parent": other_parent, "child": child_id},
                )
        finally:
            await transaction.rollback()
