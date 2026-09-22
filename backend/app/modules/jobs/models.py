"""Operational job ORM models. See docs/architecture/04-data-model.md §5."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Computed,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, TSVECTOR
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin
from app.modules.jobs.schemas import JobStatus


class SourceSystemKind(StrEnum):
    CSV_UPLOAD = "csv_upload"
    API = "api"
    SERVICETITAN = "servicetitan"
    JOBBER = "jobber"
    HOUSECALL_PRO = "housecall_pro"


class LineItemKind(StrEnum):
    PART = "part"
    LABOR = "labor"
    FEE = "fee"
    DISCOUNT = "discount"
    OTHER = "other"


SOURCE_SYSTEM_KIND = SAEnum(
    SourceSystemKind,
    name="source_system_kind",
    values_callable=lambda enum: [member.value for member in enum],
)
JOB_STATUS = SAEnum(
    JobStatus,
    name="job_status",
    values_callable=lambda enum: [member.value for member in enum],
)
LINE_ITEM_KIND = SAEnum(
    LineItemKind,
    name="line_item_kind",
    values_callable=lambda enum: [member.value for member in enum],
)


class SourceSystem(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "source_systems"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="source_systems_org_id_key"),
        UniqueConstraint("organization_id", "name", name="source_systems_org_name_key"),
    )

    kind: Mapped[SourceSystemKind] = mapped_column(SOURCE_SYSTEM_KIND, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ServiceCategory(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "service_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="service_categories_org_id_key"),
        UniqueConstraint("organization_id", "key", name="service_categories_org_key_key"),
        ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="service_categories_parent_tenant_fkey",
        ),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("service_categories.id", ondelete="SET NULL")
    )
    is_system_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))


class Job(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="jobs_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "source_system_id"],
            ["source_systems.organization_id", "source_systems.id"],
            name="jobs_source_system_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="jobs_customer_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "location_id"],
            ["locations.organization_id", "locations.id"],
            name="jobs_location_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "equipment_id"],
            ["equipment.organization_id", "equipment.id"],
            name="jobs_equipment_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "technician_id"],
            ["technicians.organization_id", "technicians.id"],
            name="jobs_technician_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "service_category_id"],
            ["service_categories.organization_id", "service_categories.id"],
            name="jobs_service_category_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "first_import_batch_id"],
            ["import_batches.organization_id", "import_batches.id"],
            name="jobs_first_import_batch_tenant_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "last_import_batch_id"],
            ["import_batches.organization_id", "import_batches.id"],
            name="jobs_last_import_batch_tenant_fkey",
        ),
        Index(
            "jobs_org_source_external_key",
            "organization_id",
            "source_system_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "jobs_org_natural_key",
            "organization_id",
            "natural_key_hash",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("jobs_org_customer_date_idx", "organization_id", "customer_id", "service_date"),
        Index(
            "jobs_org_equipment_date_idx",
            "organization_id",
            "equipment_id",
            "service_date",
            postgresql_where=text("equipment_id IS NOT NULL"),
        ),
        Index(
            "jobs_org_location_date_idx",
            "organization_id",
            "location_id",
            "service_date",
            postgresql_where=text("location_id IS NOT NULL"),
        ),
        Index(
            "jobs_org_date_id_idx",
            "organization_id",
            text("service_date DESC"),
            text("id DESC"),
        ),
        Index(
            "jobs_org_technician_date_idx",
            "organization_id",
            "technician_id",
            "service_date",
        ),
        Index("jobs_org_last_import_idx", "organization_id", "last_import_batch_id"),
        Index("jobs_search_document_idx", "search_document", postgresql_using="gin"),
    )

    source_system_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    natural_key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    first_import_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    last_import_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    equipment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    technician_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    service_category_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    job_number: Mapped[str | None] = mapped_column(Text)
    raw_service_category: Mapped[str | None] = mapped_column(Text)
    raw_job_type: Mapped[str | None] = mapped_column(Text)
    status: Mapped[JobStatus] = mapped_column(
        JOB_STATUS, nullable=False, server_default=JobStatus.UNKNOWN.value
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    service_date: Mapped[date] = mapped_column(nullable=False)
    duration_minutes: Mapped[int | None]
    summary: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    symptoms_text: Mapped[str | None] = mapped_column(Text)
    diagnosis_text: Mapped[str | None] = mapped_column(Text)
    resolution_text: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(Text)
    revenue_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    parts_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    labor_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(Text, nullable=False)
    is_warranty: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    is_no_charge: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    warranty_reference: Mapped[str | None] = mapped_column(Text)
    extra_fields: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    search_document: Mapped[object] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(summary, '') || ' ' || "
            "coalesce(description, '') || ' ' || coalesce(symptoms_text, '') || ' ' || "
            "coalesce(diagnosis_text, '') || ' ' || coalesce(resolution_text, ''))",
            persisted=True,
        ),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class JobNote(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "job_notes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="job_notes_job_fkey",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id", "job_id", "content_hash", name="job_notes_org_job_hash_key"
        ),
        Index("job_notes_org_job_idx", "organization_id", "job_id"),
    )

    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    note_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="technician")
    author_name: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    content_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class JobLineItem(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "job_line_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="job_line_items_job_fkey",
            ondelete="CASCADE",
        ),
        Index("job_line_items_org_job_idx", "organization_id", "job_id"),
        Index(
            "job_line_items_org_code_idx",
            "organization_id",
            "code",
            postgresql_where=text("code IS NOT NULL"),
        ),
    )

    job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[LineItemKind] = mapped_column(LINE_ITEM_KIND, nullable=False)
    code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, server_default="1")
    unit_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency_code: Mapped[str] = mapped_column(Text, nullable=False)
    line_number: Mapped[int | None]
