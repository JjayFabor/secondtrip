"""Technician ORM model. See docs/architecture/04-data-model.md §5."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, LargeBinary, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin


class Technician(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "technicians"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="technicians_org_id_key"),
        Index(
            "technicians_org_natural_key",
            "organization_id",
            "natural_key_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    external_id: Mapped[str | None] = mapped_column(Text)
    natural_key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    employee_code: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)
    hourly_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
