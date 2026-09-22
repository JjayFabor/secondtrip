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

Two tables need a second access path alongside the standard org-scoped
one, and get their own variant here rather than the plain `enable_rls`:

- `organization_memberships` — a user must be able to list their OWN
  memberships across every org (`GET /orgs`) before they have any single
  org's context to set. `enable_rls_with_self_access` adds an
  `OR user_id = current_setting('app.current_user_id', true)` clause.
- `organization_invitations` — resolving an invitation by its bearer
  token has to work before the caller has any org context (or
  necessarily an account) in that org at all. `enable_rls_with_token_lookup`
  adds an `OR token_hash = current_setting('app.lookup_token_hash', true)`
  clause — possession of the raw 256-bit token is the authorization for
  this one lookup, the same trust model session tokens use elsewhere.

Both extra clauses are SELECT-only in spirit: `WITH CHECK` never includes
them, so nothing can be inserted or updated "as" a self-access or
token-holding actor — only read.
"""

from __future__ import annotations

from alembic import op

_ORG_ID_EXPR = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"
_USER_ID_EXPR = "NULLIF(current_setting('app.current_user_id', true), '')::uuid"
_TOKEN_HASH_EXPR = "NULLIF(current_setting('app.lookup_token_hash', true), '')"
_WORKER_EXPR = "NULLIF(current_setting('app.worker_context', true), '') = '1'"


def _drop_policies(table_name: str) -> None:
    """Remove both the current policy names and the original Phase 2 name.

    Policy names are migration-owned identifiers, not user input. Keeping the
    legacy name here lets a forward repair migration replace the first
    implementation without needing to know which revision created the table.
    """
    for suffix in ("select", "insert", "update", "delete", "isolation"):
        op.execute(f"DROP POLICY IF EXISTS {table_name}_tenant_{suffix} ON {table_name}")


def _enable_table_rls(table_name: str) -> None:
    op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")


def _create_org_policies(table_name: str, *, select_expr: str) -> None:
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_select ON {table_name}
        FOR SELECT USING ({select_expr})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_insert ON {table_name}
        FOR INSERT WITH CHECK (organization_id = {_ORG_ID_EXPR})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_update ON {table_name}
        FOR UPDATE
        USING (organization_id = {_ORG_ID_EXPR})
        WITH CHECK (organization_id = {_ORG_ID_EXPR})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_delete ON {table_name}
        FOR DELETE USING (organization_id = {_ORG_ID_EXPR})
        """
    )


def enable_rls(table_name: str) -> None:
    _drop_policies(table_name)
    _enable_table_rls(table_name)
    _create_org_policies(table_name, select_expr=f"organization_id = {_ORG_ID_EXPR}")


def enable_rls_with_self_access(table_name: str, *, user_column: str = "user_id") -> None:
    _drop_policies(table_name)
    _enable_table_rls(table_name)
    _create_org_policies(
        table_name,
        select_expr=(f"organization_id = {_ORG_ID_EXPR} OR {user_column} = {_USER_ID_EXPR}"),
    )


def enable_rls_with_token_lookup(
    table_name: str,
    *,
    token_column: str = "token_hash",
    include_user_email: bool = False,
) -> None:
    _drop_policies(table_name)
    _enable_table_rls(table_name)
    select_expr = f"organization_id = {_ORG_ID_EXPR} OR {token_column} = {_TOKEN_HASH_EXPR}"
    if include_user_email:
        select_expr += f" OR email = (SELECT email FROM users WHERE id = {_USER_ID_EXPR})"
    _create_org_policies(
        table_name,
        select_expr=select_expr,
    )


def enable_rls_with_worker_access(table_name: str) -> None:
    """Tenant isolation plus a transaction-local path for the worker.

    Queue claims and provider-event reconciliation must inspect rows across
    organizations before they can rehydrate one tenant context. Ordinary API
    transactions never set ``app.worker_context``, so they retain the same
    fail-closed behavior as the standard policy.
    """
    _drop_policies(table_name)
    _enable_table_rls(table_name)
    select_expr = f"organization_id = {_ORG_ID_EXPR} OR {_WORKER_EXPR}"
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_select ON {table_name}
        FOR SELECT USING ({select_expr})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_insert ON {table_name}
        FOR INSERT WITH CHECK (organization_id = {_ORG_ID_EXPR} OR {_WORKER_EXPR})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_update ON {table_name}
        FOR UPDATE
        USING ({select_expr})
        WITH CHECK (organization_id = {_ORG_ID_EXPR} OR {_WORKER_EXPR})
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table_name}_tenant_delete ON {table_name}
        FOR DELETE USING ({select_expr})
        """
    )


def disable_rls(table_name: str) -> None:
    _drop_policies(table_name)
    op.execute(f"ALTER TABLE {table_name} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY")
