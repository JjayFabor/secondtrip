"""store normalized import records

Revision ID: d17f4a2c8e63
Revises: c42a7e91d5b0
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d17f4a2c8e63"
down_revision: str | None = "c42a7e91d5b0"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_rows",
        sa.Column(
            "normalized_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("import_rows", "normalized_data")
