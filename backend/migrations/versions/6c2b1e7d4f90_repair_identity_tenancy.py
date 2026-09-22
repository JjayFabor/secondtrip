"""repair identity and tenancy constraints

The first Step 3 migration created the right broad tables, but left several
integrity and isolation details for the follow-up implementation: tenant
foreign keys, soft-delete-safe email uniqueness, discovery-only RLS paths,
and the active-owner invariant. This revision is deliberately forward-only
so a database that already applied the scaffold can be repaired safely.

Revision ID: 6c2b1e7d4f90
Revises: 52ffdd774e8b
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.rls_helpers import (
    disable_rls,
    enable_rls,
    enable_rls_with_self_access,
    enable_rls_with_token_lookup,
)

revision: str = "6c2b1e7d4f90"
down_revision: str | None = "52ffdd774e8b"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_change_tokens",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("new_email", postgresql.CITEXT(), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.CheckConstraint("expires_at > created_at", name="email_change_tokens_expiry_check"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="email_change_tokens_hash_key"),
    )
    op.create_index(
        "email_change_tokens_user_consumed_idx",
        "email_change_tokens",
        ["user_id", "consumed_at"],
    )

    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("window_start", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("count >= 0", name="rate_limit_counters_count_check"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "rate_limit_counters_window_idx",
        "rate_limit_counters",
        ["window_start"],
    )

    # The scaffold used a table-wide unique constraint, which prevents a
    # deleted user's address from ever being reused. Replace it with the
    # partial uniqueness specified by the data model.
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.create_index(
        "users_email_active_key",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # This constraint was redundant (id is already the primary key) and is
    # not the composite key required by future tenant-owned relationships.
    op.drop_constraint(
        "organization_memberships_org_id_key",
        "organization_memberships",
        type_="unique",
    )

    op.create_foreign_key(
        "organization_memberships_organization_id_fkey",
        "organization_memberships",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "organization_invitations_organization_id_fkey",
        "organization_invitations",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "audit_events_organization_id_fkey",
        "audit_events",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_check_constraint(
        "users_status_check",
        "users",
        "status IN ('pending_verification', 'active', 'suspended', 'deactivated')",
    )
    op.create_check_constraint(
        "organizations_status_check",
        "organizations",
        "status IN ('active', 'suspended', 'pending_deletion')",
    )
    op.create_check_constraint(
        "organization_memberships_role_check",
        "organization_memberships",
        "role IN ('owner', 'admin', 'manager', 'member')",
    )
    op.create_check_constraint(
        "organization_invitations_role_check",
        "organization_invitations",
        "role IN ('owner', 'admin', 'manager', 'member')",
    )
    op.create_check_constraint(
        "email_verification_tokens_expiry_check",
        "email_verification_tokens",
        "expires_at > created_at",
    )

    # Rebuild all three tenant policies so self/token discovery is SELECT-only.
    enable_rls_with_self_access("organization_memberships")
    enable_rls_with_token_lookup("organization_invitations")
    enable_rls("audit_events")
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM secondtrip_app")

    # The service layer locks the organization row for normal mutations; this
    # deferred trigger is the database backstop, including concurrent direct
    # writes. The advisory lock serializes owner checks at commit time.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION secondtrip_assert_active_owner(p_org_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtext(p_org_id::text));
            IF EXISTS (
                SELECT 1
                FROM organizations
                WHERE id = p_org_id AND status = 'active'
            ) AND NOT EXISTS (
                SELECT 1
                FROM organization_memberships
                WHERE organization_id = p_org_id
                  AND role = 'owner'
                  AND revoked_at IS NULL
            ) THEN
                RAISE EXCEPTION 'organization must have at least one active owner'
                    USING ERRCODE = '23514';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION secondtrip_check_active_owner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM secondtrip_assert_active_owner(OLD.organization_id);
                RETURN OLD;
            END IF;

            PERFORM secondtrip_assert_active_owner(NEW.organization_id);
            IF TG_OP = 'UPDATE'
               AND OLD.organization_id IS DISTINCT FROM NEW.organization_id THEN
                PERFORM secondtrip_assert_active_owner(OLD.organization_id);
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION secondtrip_check_organization_owner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM secondtrip_assert_active_owner(NEW.id);
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER organization_memberships_owner_guard
        AFTER INSERT OR UPDATE OR DELETE ON organization_memberships
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION secondtrip_check_active_owner()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER organizations_owner_guard
        AFTER INSERT OR UPDATE OF status ON organizations
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION secondtrip_check_organization_owner()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS organizations_owner_guard ON organizations")
    op.execute(
        "DROP TRIGGER IF EXISTS organization_memberships_owner_guard ON organization_memberships"
    )
    op.execute("DROP FUNCTION IF EXISTS secondtrip_check_active_owner()")
    op.execute("DROP FUNCTION IF EXISTS secondtrip_check_organization_owner()")
    op.execute("DROP FUNCTION IF EXISTS secondtrip_assert_active_owner(uuid)")

    disable_rls("audit_events")
    disable_rls("organization_invitations")
    disable_rls("organization_memberships")
    op.execute("GRANT UPDATE, DELETE ON audit_events TO secondtrip_app")

    op.drop_constraint("email_verification_tokens_expiry_check", "email_verification_tokens")
    op.drop_constraint("organization_invitations_role_check", "organization_invitations")
    op.drop_constraint("organization_memberships_role_check", "organization_memberships")
    op.drop_constraint("organizations_status_check", "organizations")
    op.drop_constraint("users_status_check", "users")

    op.drop_constraint(
        "audit_events_organization_id_fkey", "audit_events", type_="foreignkey"
    )
    op.drop_constraint(
        "organization_invitations_organization_id_fkey",
        "organization_invitations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "organization_memberships_organization_id_fkey",
        "organization_memberships",
        type_="foreignkey",
    )

    op.drop_index("users_email_active_key", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_unique_constraint(
        "organization_memberships_org_id_key",
        "organization_memberships",
        ["organization_id", "id"],
    )

    op.drop_index("rate_limit_counters_window_idx", table_name="rate_limit_counters")
    op.drop_table("rate_limit_counters")
    op.drop_index("email_change_tokens_user_consumed_idx", table_name="email_change_tokens")
    op.drop_table("email_change_tokens")

    # Keep the equivalent split policies when downgrading with the current
    # helper implementation; the prior migration's semantics remain intact.
    enable_rls_with_self_access("organization_memberships")
    enable_rls_with_token_lookup("organization_invitations")
    enable_rls("audit_events")
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM secondtrip_app")
