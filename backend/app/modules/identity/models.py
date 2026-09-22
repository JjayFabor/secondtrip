"""Identity ORM models. See docs/architecture/04-data-model.md §3.

Not tenant-owned — no `organization_id`, no RLS. A person is a person;
they may belong to several organizations via organization_memberships.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, PrimaryKeyMixin, TimestampMixin


class UserStatus(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class User(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "users_email_active_key",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("users_status_idx", "status"),
    )

    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=UserStatus.PENDING_VERIFICATION.value
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    timezone: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    credentials: Mapped[UserCredentials] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class UserCredentials(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    password_updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    failed_attempt_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    user: Mapped[User] = relationship(back_populates="credentials")


class UserSession(Base, PrimaryKeyMixin):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("user_sessions_user_id_revoked_at_idx", "user_id", "revoked_at"),)

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ip_hash: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)


class EmailVerificationToken(Base, PrimaryKeyMixin):
    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        Index("email_verification_tokens_user_consumed_idx", "user_id", "consumed_at"),
        CheckConstraint("expires_at > created_at", name="email_verification_tokens_expiry_check"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class PasswordResetToken(Base, PrimaryKeyMixin):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("password_reset_tokens_user_consumed_idx", "user_id", "consumed_at"),
        CheckConstraint("expires_at > created_at", name="password_reset_tokens_expiry_check"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class EmailChangeToken(Base, PrimaryKeyMixin):
    __tablename__ = "email_change_tokens"
    __table_args__ = (
        Index("email_change_tokens_user_consumed_idx", "user_id", "consumed_at"),
        CheckConstraint("expires_at > created_at", name="email_change_tokens_expiry_check"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    new_email: Mapped[str] = mapped_column(CITEXT, nullable=False)


class RateLimitCounter(Base):
    """Global operational counter; organization-scoped keys are namespaced
    by the rate-limit service rather than exposing tenant data in this table.
    """

    __tablename__ = "rate_limit_counters"
    __table_args__ = (
        Index("rate_limit_counters_window_idx", "window_start"),
        CheckConstraint("count >= 0", name="rate_limit_counters_count_check"),
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    window_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
