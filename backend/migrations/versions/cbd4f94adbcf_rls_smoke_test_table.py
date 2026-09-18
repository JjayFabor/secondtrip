"""rls smoke test table

Proves the tenant-isolation mechanism end to end (RLS + the non-owner app
role + the enable_rls helper) before any real business table exists. See
docs/architecture/21-implementation-sequencing.md Phase 2 exit criteria
and tests/security/test_rls.py, which is the actual proof — this
migration only creates the fixture.

Phase 3 replaces this with real tenant tables (organization_memberships,
customers, jobs, ...) built the exact same way: create the table, then
call enable_rls(table_name) as the last step.

Revision ID: cbd4f94adbcf
Revises:
Create Date: 2026-09-18 13:32:47.497134
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.rls_helpers import disable_rls, enable_rls

revision: str = "cbd4f94adbcf"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE_NAME = "_rls_smoke_test"


def upgrade() -> None:
    # gen_random_uuid() is a Postgres core builtin since PG13 — no
    # extension needed.
    op.create_table(
        TABLE_NAME,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
    )
    op.create_index(
        f"{TABLE_NAME}_org_idx", TABLE_NAME, ["organization_id"]
    )
    enable_rls(TABLE_NAME)


def downgrade() -> None:
    disable_rls(TABLE_NAME)
    op.drop_table(TABLE_NAME)
