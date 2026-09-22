"""Tenant-scoped HTTP idempotency records required by API conventions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, LargeBinary, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin


class ApiIdempotencyRecord(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "api_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "route", "idempotency_key", name="api_idempotency_route_key"
        ),
        Index("api_idempotency_expires_idx", "expires_at"),
    )

    route: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_status: Mapped[int | None]
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    response_headers: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
