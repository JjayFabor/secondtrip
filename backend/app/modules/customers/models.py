"""Customer/location/equipment ORM models. See docs/architecture/04-data-model.md §4."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin


class Customer(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="customers_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "source_system_id"],
            ["source_systems.organization_id", "source_systems.id"],
            name="customers_source_system_fkey",
        ),
        Index(
            "customers_org_source_external_key",
            "organization_id",
            "source_system_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "customers_org_natural_key",
            "organization_id",
            "natural_key_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("customers_org_normalized_name_idx", "organization_id", "normalized_name"),
        Index(
            "customers_org_phone_idx",
            "organization_id",
            "phone_e164",
            postgresql_where=text("phone_e164 IS NOT NULL"),
        ),
    )

    source_system_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_id: Mapped[str | None] = mapped_column(Text)
    natural_key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_type: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(CITEXT)
    phone_raw: Mapped[str | None] = mapped_column(Text)
    phone_e164: Mapped[str | None] = mapped_column(Text)
    account_number: Mapped[str | None] = mapped_column(Text)
    first_seen_job_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_seen_job_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    job_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Location(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="locations_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="locations_customer_fkey",
        ),
        Index(
            "locations_org_customer_address_key",
            "organization_id",
            "customer_id",
            "address_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("locations_org_postal_code_idx", "organization_id", "postal_code"),
    )

    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_id: Mapped[str | None] = mapped_column(Text)
    address_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    address_line1: Mapped[str | None] = mapped_column(Text)
    address_line2: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class Equipment(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "equipment"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="equipment_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="equipment_customer_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="equipment_location_fkey",
        ),
        Index(
            "equipment_org_natural_key",
            "organization_id",
            "natural_key_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("equipment_org_location_idx", "organization_id", "location_id"),
        Index(
            "equipment_org_serial_idx",
            "organization_id",
            "serial_number",
            postgresql_where=text("serial_number IS NOT NULL"),
        ),
    )

    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    external_id: Mapped[str | None] = mapped_column(Text)
    natural_key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    asset_tag: Mapped[str | None] = mapped_column(Text)
    serial_number: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    equipment_type: Mapped[str | None] = mapped_column(Text)
    installed_on: Mapped[date | None]
    warranty_expires_on: Mapped[date | None]
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
