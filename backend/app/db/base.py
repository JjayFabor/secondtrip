"""Declarative base and shared mixins.

See docs/architecture/04-data-model.md §1. UUIDv7 primary keys generated in
Python (app.core.ids.new_id — the app default; gen_random_uuid() stays on
the column as a safety net for out-of-band inserts, per ADR-010). All
timestamps are timestamptz in UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_id


class Base(DeclarativeBase):
    pass


class PrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=new_id,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("now()"),
        nullable=False,
    )


class TenantMixin:
    """Every tenant-owned table. organization_id is NOT NULL and RLS is
    enabled + forced on the table in its migration — see
    migrations/rls_helpers.py and CLAUDE.md rule 1."""

    organization_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
