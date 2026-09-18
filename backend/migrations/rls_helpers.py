"""RLS migration helpers — see docs/architecture/02-multi-tenancy.md §2 and
CLAUDE.md rule 1.

`enable_rls` is the ONLY way a migration should turn on RLS for a tenant
table: it applies both ENABLE and FORCE together, which is the detail
that's easy to get wrong (FORCE is what stops the table's owner — the
role every migration runs as — from bypassing its own policy) and adds a
standard tenant-isolation policy using `current_setting(..., true)`, whose
`true` third argument means a query issued before the GUC is set at all
returns zero rows instead of raising.

The policy wraps that call in `NULLIF(..., '')`: `set_config(key, NULL,
true)` — the SQL way to clear a GUC mid-session — does not produce SQL
NULL, it produces an empty string, and `''::uuid` raises rather than
comparing false. `NULLIF` maps that empty string back to true NULL before
the cast, so "never set" and "explicitly cleared" both degrade to zero
rows, matching what this module (and the architecture docs) actually
promise. Verified by hand against a live Postgres session — see
tests/security/test_rls.py.
"""

from __future__ import annotations

from alembic import op

_ORG_ID_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def enable_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_isolation ON {table_name}
        USING (organization_id = {_ORG_ID_EXPR})
        WITH CHECK (organization_id = {_ORG_ID_EXPR})
        """
    )


def disable_rls(table_name: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_isolation ON {table_name}")
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
