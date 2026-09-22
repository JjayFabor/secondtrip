"""index import-row job links

Revision ID: c42a7e91d5b0
Revises: b31c8f6d2a40
Create Date: 2026-09-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c42a7e91d5b0"
down_revision: str | None = "b31c8f6d2a40"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "import_rows_org_job_idx",
        "import_rows",
        ["organization_id", "job_id"],
    )


def downgrade() -> None:
    op.drop_index("import_rows_org_job_idx", table_name="import_rows")
