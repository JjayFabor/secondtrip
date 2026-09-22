"""allow verified users to read invitations addressed to their email

Revision ID: 8e3a1f2c7b90
Revises: 6c2b1e7d4f90
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from migrations.rls_helpers import enable_rls_with_token_lookup

revision: str = "8e3a1f2c7b90"
down_revision: str | None = "6c2b1e7d4f90"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    enable_rls_with_token_lookup(
        "organization_invitations",
        include_user_email=True,
    )


def downgrade() -> None:
    enable_rls_with_token_lookup("organization_invitations")
