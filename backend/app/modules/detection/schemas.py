"""Detection enums and API schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.schemas import JobStatus


class RuleKind(StrEnum):
    ADDITIVE = "additive"
    MULTIPLIER = "multiplier"
    GATE = "gate"
    VETO = "veto"


class SignalOutcome(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    NOT_EVALUABLE = "not_evaluable"


class ScoreBand(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalValueType(StrEnum):
    BOOLEAN = "boolean"
    NUMERIC = "numeric"
    RATIO = "ratio"
    CATEGORICAL = "categorical"


class DetectionTrigger(StrEnum):
    IMPORT_COMPLETED = "import_completed"
    RULES_CHANGED = "rules_changed"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class DetectionRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateWorkflowStatus(StrEnum):
    OPEN = "open"
    IN_REVIEW = "in_review"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class CandidateSuppressionReason(StrEnum):
    SIGNAL_VETO = "signal_veto"
    OUT_OF_WINDOW = "out_of_window"


class CategoryOutcome(StrEnum):
    REWORK = "rework"
    NOT_REWORK = "not_rework"
    UNCERTAIN = "uncertain"


class ReviewDecision(StrEnum):
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNCERTAIN = "uncertain"


class CandidateSort(StrEnum):
    SCORE = "-score"
    DAYS_BETWEEN = "-days_between"
    DETECTED_AT = "-detected_at"


class ReworkCategoryOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    key: str
    label: str
    description: str | None
    outcome: CategoryOutcome
    counts_toward_cost: bool
    is_system_default: bool
    is_active: bool
    color: str | None
    sort_order: int


class RootCauseOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    key: str
    label: str
    parent_id: UUID | None
    is_system_default: bool
    is_active: bool
    sort_order: int


class CreateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReviewDecision
    category_id: UUID | None = None
    root_cause_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class ReworkReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    candidate_id: UUID
    decision: ReviewDecision
    category_id: UUID | None
    root_cause_id: UUID | None
    note: str | None
    reviewed_by_user_id: UUID
    score_at_review: Decimal | None
    rule_set_id_at_review: UUID | None
    decided_at: datetime
    superseded_by_review_id: UUID | None
    created_at: datetime


class CandidateJobOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    external_id: str | None
    job_number: str | None
    customer_id: UUID | None
    location_id: UUID | None
    equipment_id: UUID | None
    technician_id: UUID | None
    technician_name: str | None
    status: JobStatus
    service_date: date
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    raw_service_category: str | None
    raw_job_type: str | None
    summary: str | None
    description: str | None
    symptoms_text: str | None
    diagnosis_text: str | None
    resolution_text: str | None
    invoice_number: str | None
    revenue_amount: Decimal | None
    parts_amount: Decimal | None
    labor_amount: Decimal | None
    currency_code: str
    is_warranty: bool
    is_no_charge: bool
    warranty_reference: str | None


class CandidateCustomerOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    display_name: str
    account_number: str | None


class CandidateEquipmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    asset_tag: str | None
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    equipment_type: str | None


class CandidateSignalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    rule_kind: RuleKind
    outcome: SignalOutcome
    strength: Decimal
    weight_applied: Decimal
    contribution: Decimal
    explanation: str
    raw_value: dict[str, object] | None


class CandidateSummaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    score: Decimal
    band: ScoreBand
    days_between: int
    is_suppressed: bool
    suppression_reason: CandidateSuppressionReason | None
    suppressed_by_signal_key: str | None
    workflow_status: CandidateWorkflowStatus
    prior_job: CandidateJobOut
    followup_job: CandidateJobOut
    customer: CandidateCustomerOut | None
    equipment: CandidateEquipmentOut | None
    current_review: ReworkReviewOut | None
    top_signals: list[CandidateSignalOut]
    detected_at: datetime


class CandidateDetailOut(CandidateSummaryOut):
    signals: list[CandidateSignalOut]


class CandidatePageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None
    has_more: bool
    limit: int


class CandidateListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[CandidateSummaryOut]
    page: CandidatePageOut
