"""Import ORM models. See docs/architecture/04-data-model.md §10."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin


class ImportStatus(StrEnum):
    AWAITING_FILE = "awaiting_file"
    UPLOADED = "uploaded"
    PROFILING = "profiling"
    AWAITING_MAPPING = "awaiting_mapping"
    VALIDATING = "validating"
    VALIDATED = "validated"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportRowStatus(StrEnum):
    PENDING = "pending"
    IMPORTED = "imported"
    UPDATED = "updated"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SKIPPED_FILTERED = "skipped_filtered"
    WARNING = "warning"
    ERROR = "error"


IMPORT_STATUS = SAEnum(
    ImportStatus,
    name="import_status",
    values_callable=lambda enum: [member.value for member in enum],
)
IMPORT_ROW_STATUS = SAEnum(
    ImportRowStatus,
    name="import_row_status",
    values_callable=lambda enum: [member.value for member in enum],
)


class ImportColumnMapping(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "import_column_mappings"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="import_column_mappings_org_id_key"),
        UniqueConstraint("organization_id", "name", name="import_column_mappings_org_name_key"),
        ForeignKeyConstraint(
            ["organization_id", "source_system_id"],
            ["source_systems.organization_id", "source_systems.id"],
            name="import_column_mappings_source_system_tenant_fkey",
        ),
        Index("import_column_mappings_org_signature_idx", "organization_id", "signature"),
    )

    source_system_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("source_systems.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mapping: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    options: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    signature: Mapped[str | None] = mapped_column(Text)
    usage_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ImportBatch(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "import_batches"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="import_batches_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "source_system_id"],
            ["source_systems.organization_id", "source_systems.id"],
            name="import_batches_source_system_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "template_id"],
            ["import_column_mappings.organization_id", "import_column_mappings.id"],
            name="import_batches_template_tenant_fkey",
        ),
        ForeignKeyConstraint(
            ["organization_id", "duplicate_of_batch_id"],
            ["import_batches.organization_id", "import_batches.id"],
            name="import_batches_duplicate_of_tenant_fkey",
        ),
        Index(
            "import_batches_org_file_hash_key",
            "organization_id",
            "file_sha256",
            unique=True,
            postgresql_where=text(
                "file_sha256 IS NOT NULL AND deleted_at IS NULL AND duplicate_of_batch_id IS NULL"
            ),
        ),
        Index(
            "import_batches_org_created_idx",
            "organization_id",
            text("created_at DESC"),
        ),
        Index(
            "import_batches_org_active_idx",
            "organization_id",
            "status",
            postgresql_where=text("status IN ('queued', 'processing')"),
        ),
    )

    source_system_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ImportStatus] = mapped_column(
        IMPORT_STATUS, nullable=False, server_default=ImportStatus.AWAITING_FILE.value
    )
    original_filename: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    file_sha256: Mapped[bytes | None] = mapped_column(LargeBinary)
    duplicate_of_batch_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL")
    )
    encoding: Mapped[str | None] = mapped_column(Text)
    delimiter: Mapped[str | None] = mapped_column(String(1))
    has_header: Mapped[bool | None]
    detected_columns: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    sample_rows: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    profile_issues: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    mapping: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    template_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("import_column_mappings.id", ondelete="SET NULL"),
    )
    total_rows: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    processed_rows: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    created_jobs: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    updated_jobs: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    skipped_rows: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    warning_rows: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    error_rows: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    error_report_key: Mapped[str | None] = mapped_column(Text)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    @property
    def error_report_ready(self) -> bool:
        """Expose readiness without leaking the private object-storage key."""
        return self.error_report_key is not None


class ImportRow(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "import_rows"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "import_batch_id"],
            ["import_batches.organization_id", "import_batches.id"],
            name="import_rows_batch_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="import_rows_job_tenant_fkey",
        ),
        UniqueConstraint("import_batch_id", "row_number", name="import_rows_batch_row_key"),
        Index("import_rows_batch_status_idx", "import_batch_id", "status"),
        Index("import_rows_org_batch_idx", "organization_id", "import_batch_id"),
        Index("import_rows_org_job_idx", "organization_id", "job_id"),
    )

    import_batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    row_number: Mapped[int] = mapped_column(nullable=False)
    raw_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    normalized_data: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    row_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[ImportRowStatus] = mapped_column(
        IMPORT_ROW_STATUS, nullable=False, server_default=ImportRowStatus.PENDING.value
    )
    issues: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
