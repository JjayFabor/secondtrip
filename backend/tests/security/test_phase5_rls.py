from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

PHASE5_TENANT_TABLES = {
    "candidate_score_history",
    "candidate_signals",
    "detection_rule_sets",
    "detection_rules",
    "detection_runs",
    "rework_candidates",
}


async def test_every_phase5_tenant_table_has_forced_rls(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(:table_names)"
                ),
                {"table_names": sorted(PHASE5_TENANT_TABLES)},
            )
        ).all()

    assert {row.relname for row in rows} == PHASE5_TENANT_TABLES
    assert all(row.relrowsecurity and row.relforcerowsecurity for row in rows)


async def test_phase5_tables_are_not_owned_by_app_role(owner_engine: AsyncEngine) -> None:
    async with owner_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT tablename, tableowner FROM pg_tables "
                    "WHERE tablename = ANY(:table_names)"
                ),
                {"table_names": sorted(PHASE5_TENANT_TABLES)},
            )
        ).all()

    assert {row.tablename for row in rows} == PHASE5_TENANT_TABLES
    assert all(row.tableowner != "secondtrip_app" for row in rows)
