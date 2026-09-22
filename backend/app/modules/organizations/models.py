"""Organizations ORM models. See docs/architecture/04-data-model.md §3.

`Organization` itself is not tenant-owned (it IS the tenant — no RLS).
`OrganizationMembership` and `OrganizationInvitation` get the dual-clause
RLS policies from migrations/rls_helpers.py — see that module's docstring
for why the standard single-clause policy doesn't fit either table.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.permissions import OrganizationRole
from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin


class OrganizationStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_DELETION = "pending_deletion"


class Organization(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"
    __table_args__ = (UniqueConstraint("slug", name="organizations_slug_key"),)

    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="UTC")
    currency_code: Mapped[str] = mapped_column(Text, nullable=False, server_default="USD")
    industry_key: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=OrganizationStatus.ACTIVE.value
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class OrganizationMembership(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        Index(
            "organization_memberships_org_user_active_idx",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "organization_memberships_user_active_idx",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "organization_memberships_org_role_active_idx",
            "organization_id",
            "role",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'manager', 'member')",
            name="organization_memberships_role_check",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    joined_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class OrganizationInvitation(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "organization_invitations"
    __table_args__ = (
        Index(
            "organization_invitations_org_email_pending_idx",
            "organization_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'manager', 'member')",
            name="organization_invitations_role_check",
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=OrganizationRole.MEMBER.value
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
