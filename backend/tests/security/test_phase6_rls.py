from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

PHASE6_TENANT_TABLES = {"rework_categories", "root_causes", "rework_reviews"}


async def test_every_phase6_tenant_table_has_forced_rls(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:table_names)"
                ),
                {"table_names": sorted(PHASE6_TENANT_TABLES)},
            )
        ).all()

    assert {row.relname for row in rows} == PHASE6_TENANT_TABLES
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)


async def test_review_table_grants_enforce_append_only_updates(
    owner_engine: AsyncEngine,
) -> None:
    async with owner_engine.connect() as connection:
        privileges = (
            await connection.execute(
                text(
                    "SELECT "
                    "has_table_privilege('secondtrip_app', 'rework_reviews', 'DELETE'), "
                    "has_table_privilege('secondtrip_app', 'rework_reviews', 'UPDATE'), "
                    "has_column_privilege('secondtrip_app', 'rework_reviews', "
                    "'superseded_by_review_id', 'UPDATE'), "
                    "has_column_privilege('secondtrip_app', 'rework_reviews', "
                    "'decision', 'UPDATE')"
                )
            )
        ).one()

    assert privileges == (False, False, True, False)
