"""Audit ORM model. See docs/architecture/13-audit.md.

Append-only, enforced by Postgres grants (the migration REVOKEs
UPDATE/DELETE from secondtrip_app on this table), not just convention —
see the migration for this table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin


class AuditEvent(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_events_org_occurred_idx", "organization_id", "occurred_at"),
        Index("audit_events_org_resource_idx", "organization_id", "resource_type", "resource_id"),
        Index("audit_events_org_action_occurred_idx", "organization_id", "action", "occurred_at"),
    )

    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_label: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    changes: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
