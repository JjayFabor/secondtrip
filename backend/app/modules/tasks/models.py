"""Background-job ORM model. See docs/architecture/04-data-model.md §11."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TimestampMixin


class BackgroundJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


BACKGROUND_JOB_STATUS = SAEnum(
    BackgroundJobStatus,
    name="bg_job_status",
    values_callable=lambda enum: [member.value for member in enum],
)


class BackgroundJob(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "background_jobs"
    __table_args__ = (
        Index(
            "background_jobs_active_idempotency_key",
            "job_type",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL AND status <> 'failed'"),
        ),
        Index(
            "background_jobs_claim_idx",
            "status",
            "run_at",
            "priority",
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "background_jobs_stale_idx",
            "status",
            "heartbeat_at",
            postgresql_where=text("status = 'processing'"),
        ),
        Index(
            "background_jobs_org_type_created_idx",
            "organization_id",
            "job_type",
            text("created_at DESC"),
        ),
    )

    organization_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[BackgroundJobStatus] = mapped_column(
        BACKGROUND_JOB_STATUS,
        nullable=False,
        server_default=BackgroundJobStatus.QUEUED.value,
    )
    priority: Mapped[int] = mapped_column(nullable=False, server_default=text("100"))
    run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("5"))
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    last_error: Mapped[str | None] = mapped_column(Text)
    enqueued_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    correlation_id: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
