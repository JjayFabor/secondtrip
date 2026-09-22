"""add candidate suppression reason

Revision ID: e8b7c6d5a4f3
Revises: 375da324b73d
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e8b7c6d5a4f3"
down_revision: str | None = "375da324b73d"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SUPPRESSION_REASON_ENUM = postgresql.ENUM(
    "signal_veto",
    "out_of_window",
    name="candidate_suppression_reason",
    create_type=False,
)


def upgrade() -> None:
    SUPPRESSION_REASON_ENUM.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "rework_candidates",
        sa.Column("suppression_reason", SUPPRESSION_REASON_ENUM, nullable=True),
    )
    op.execute(
        "UPDATE rework_candidates SET suppression_reason = 'signal_veto' "
        "WHERE is_suppressed"
    )
    op.create_check_constraint(
        "rework_candidates_suppression_reason_required",
        "rework_candidates",
        "(is_suppressed AND suppression_reason IS NOT NULL) OR "
        "(NOT is_suppressed AND suppression_reason IS NULL)",
    )
    op.create_check_constraint(
        "rework_candidates_suppression_source_valid",
        "rework_candidates",
        "(suppression_reason = 'signal_veto' AND suppressed_by_signal_key IS NOT NULL) OR "
        "(suppression_reason = 'out_of_window' AND suppressed_by_signal_key IS NULL) OR "
        "(suppression_reason IS NULL AND suppressed_by_signal_key IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "rework_candidates_suppression_source_valid",
        "rework_candidates",
        type_="check",
    )
    op.drop_constraint(
        "rework_candidates_suppression_reason_required",
        "rework_candidates",
        type_="check",
    )
    op.drop_column("rework_candidates", "suppression_reason")
    SUPPRESSION_REASON_ENUM.drop(op.get_bind(), checkfirst=True)
