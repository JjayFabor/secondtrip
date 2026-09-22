"""reconcile identity indexes with ORM metadata

Revision ID: a47d9c3e1f20
Revises: 8e3a1f2c7b90
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "a47d9c3e1f20"
down_revision: str | None = "8e3a1f2c7b90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "email_verification_tokens_user_consumed_idx",
        "email_verification_tokens",
        ["user_id", "consumed_at"],
    )
    op.create_index(
        "password_reset_tokens_user_consumed_idx",
        "password_reset_tokens",
        ["user_id", "consumed_at"],
    )
    op.create_index("users_status_idx", "users", ["status"])


def downgrade() -> None:
    op.drop_index("users_status_idx", table_name="users")
    op.drop_index(
        "password_reset_tokens_user_consumed_idx",
        table_name="password_reset_tokens",
    )
    op.drop_index(
        "email_verification_tokens_user_consumed_idx",
        table_name="email_verification_tokens",
    )
