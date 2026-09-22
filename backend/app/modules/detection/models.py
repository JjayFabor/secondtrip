"""Detection ORM models. See docs/architecture/04-data-model.md §6."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, PrimaryKeyMixin, TenantMixin, TimestampMixin
from app.modules.detection.schemas import (
    CandidateSuppressionReason,
    CandidateWorkflowStatus,
    CategoryOutcome,
    DetectionRunStatus,
    DetectionTrigger,
    ReviewDecision,
    RuleKind,
    ScoreBand,
    SignalOutcome,
    SignalValueType,
)


def _enum_values(enum: type[object]) -> list[str]:
    return [str(member.value) for member in enum]  # type: ignore[attr-defined]


SIGNAL_VALUE_TYPE = SAEnum(
    SignalValueType,
    name="signal_value_type",
    values_callable=_enum_values,
)
RULE_KIND = SAEnum(RuleKind, name="rule_kind", values_callable=_enum_values)
DETECTION_TRIGGER = SAEnum(
    DetectionTrigger,
    name="detection_trigger",
    values_callable=_enum_values,
)
DETECTION_RUN_STATUS = SAEnum(
    DetectionRunStatus,
    name="run_status",
    values_callable=_enum_values,
)
SCORE_BAND = SAEnum(ScoreBand, name="score_band", values_callable=_enum_values)
CANDIDATE_WORKFLOW_STATUS = SAEnum(
    CandidateWorkflowStatus,
    name="candidate_workflow_status",
    values_callable=_enum_values,
)
CANDIDATE_SUPPRESSION_REASON = SAEnum(
    CandidateSuppressionReason,
    name="candidate_suppression_reason",
    values_callable=_enum_values,
)
SIGNAL_OUTCOME = SAEnum(
    SignalOutcome,
    name="signal_outcome",
    values_callable=_enum_values,
)
CATEGORY_OUTCOME = SAEnum(
    CategoryOutcome,
    name="category_outcome",
    values_callable=_enum_values,
)
REVIEW_DECISION = SAEnum(
    ReviewDecision,
    name="review_decision",
    values_callable=_enum_values,
)


class DetectionSignalDefinition(Base):
    __tablename__ = "detection_signal_definitions"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[SignalValueType] = mapped_column(SIGNAL_VALUE_TYPE, nullable=False)
    default_weight: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    default_params: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    supported_kinds: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))


class DetectionRuleSet(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "detection_rule_sets"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="detection_rule_sets_org_id_key"),
        UniqueConstraint(
            "organization_id",
            "version_number",
            name="detection_rule_sets_org_version_key",
        ),
        Index(
            "detection_rule_sets_org_active_key",
            "organization_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        CheckConstraint("version_number > 0", name="detection_rule_sets_version_positive"),
        CheckConstraint("window_days > 0", name="detection_rule_sets_window_positive"),
        CheckConstraint(
            "min_score_to_surface BETWEEN 0 AND 100",
            name="detection_rule_sets_surface_score_range",
        ),
        CheckConstraint(
            "max_followups_per_job > 0",
            name="detection_rule_sets_followups_positive",
        ),
    )

    version_number: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    window_days: Mapped[int] = mapped_column(nullable=False, server_default=text("30"))
    min_score_to_surface: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("40")
    )
    max_followups_per_job: Mapped[int] = mapped_column(nullable=False, server_default=text("25"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class DetectionRule(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "detection_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="detection_rules_rule_set_fkey",
            ondelete="CASCADE",
        ),
        UniqueConstraint("rule_set_id", "signal_key", name="detection_rules_set_signal_key"),
        CheckConstraint("weight >= 0", name="detection_rules_weight_nonnegative"),
    )

    rule_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    signal_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("detection_signal_definitions.key", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[RuleKind] = mapped_column(RULE_KIND, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False, server_default=text("0"))
    params: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))


class DetectionRun(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "detection_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="detection_runs_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="detection_runs_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        Index("detection_runs_org_started_idx", "organization_id", text("started_at DESC")),
        CheckConstraint("pairs_evaluated >= 0", name="detection_runs_pairs_nonnegative"),
        CheckConstraint("candidates_created >= 0", name="detection_runs_created_nonnegative"),
        CheckConstraint("candidates_updated >= 0", name="detection_runs_updated_nonnegative"),
        CheckConstraint(
            "candidates_suppressed >= 0",
            name="detection_runs_suppressed_nonnegative",
        ),
    )

    rule_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    trigger: Mapped[DetectionTrigger] = mapped_column(DETECTION_TRIGGER, nullable=False)
    scope: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[DetectionRunStatus] = mapped_column(
        DETECTION_RUN_STATUS,
        nullable=False,
        server_default=DetectionRunStatus.QUEUED.value,
    )
    pairs_evaluated: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    candidates_created: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    candidates_updated: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    candidates_suppressed: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    background_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("background_jobs.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)


class ReworkCandidate(Base, PrimaryKeyMixin, TenantMixin, TimestampMixin):
    __tablename__ = "rework_candidates"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="rework_candidates_org_id_key"),
        UniqueConstraint(
            "organization_id",
            "prior_job_id",
            "followup_job_id",
            name="rework_candidates_org_pair_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "prior_job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="rework_candidates_prior_job_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "followup_job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="rework_candidates_followup_job_fkey",
            ondelete="CASCADE",
        ),
        CheckConstraint("prior_job_id <> followup_job_id", name="rework_candidates_distinct_jobs"),
        CheckConstraint("days_between >= 0", name="rework_candidates_days_nonnegative"),
        CheckConstraint(
            "current_normalized_score IS NULL OR current_normalized_score BETWEEN 0 AND 100",
            name="rework_candidates_normalized_score_range",
        ),
        CheckConstraint(
            "(is_suppressed AND suppression_reason IS NOT NULL) OR "
            "(NOT is_suppressed AND suppression_reason IS NULL)",
            name="rework_candidates_suppression_reason_required",
        ),
        CheckConstraint(
            "(suppression_reason = 'signal_veto' AND suppressed_by_signal_key IS NOT NULL) OR "
            "(suppression_reason = 'out_of_window' AND suppressed_by_signal_key IS NULL) OR "
            "(suppression_reason IS NULL AND suppressed_by_signal_key IS NULL)",
            name="rework_candidates_suppression_source_valid",
        ),
        Index(
            "rework_candidates_org_review_queue_idx",
            "organization_id",
            text("current_normalized_score DESC"),
            text("id DESC"),
            postgresql_where=text("NOT is_suppressed AND workflow_status = 'open'"),
        ),
        Index(
            "rework_candidates_org_workflow_evaluated_idx",
            "organization_id",
            "workflow_status",
            text("last_evaluated_at DESC"),
        ),
        Index("rework_candidates_org_followup_idx", "organization_id", "followup_job_id"),
        Index("rework_candidates_org_prior_idx", "organization_id", "prior_job_id"),
        Index(
            "rework_candidates_org_equipment_idx",
            "organization_id",
            "equipment_id",
            postgresql_where=text("equipment_id IS NOT NULL"),
        ),
        Index(
            "rework_candidates_org_run_idx",
            "organization_id",
            "current_detection_run_id",
        ),
    )

    prior_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    followup_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    customer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    location_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    equipment_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    technician_prior_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    technician_followup_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    days_between: Mapped[int] = mapped_column(nullable=False)
    current_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    current_normalized_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    score_band: Mapped[ScoreBand | None] = mapped_column(SCORE_BAND)
    is_suppressed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    suppression_reason: Mapped[CandidateSuppressionReason | None] = mapped_column(
        CANDIDATE_SUPPRESSION_REASON
    )
    suppressed_by_signal_key: Mapped[str | None] = mapped_column(
        Text, ForeignKey("detection_signal_definitions.key", ondelete="SET NULL")
    )
    workflow_status: Mapped[CandidateWorkflowStatus] = mapped_column(
        CANDIDATE_WORKFLOW_STATUS,
        nullable=False,
        server_default=CandidateWorkflowStatus.OPEN.value,
    )
    current_rule_set_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("detection_rule_sets.id", ondelete="SET NULL")
    )
    current_detection_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("detection_runs.id", ondelete="SET NULL")
    )
    first_detected_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class CandidateSignal(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "candidate_signals"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="candidate_signals_candidate_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "detection_run_id"],
            ["detection_runs.organization_id", "detection_runs.id"],
            name="candidate_signals_run_fkey",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "candidate_id",
            "detection_run_id",
            "signal_key",
            name="candidate_signals_candidate_run_signal_key",
        ),
        CheckConstraint("strength BETWEEN 0 AND 1", name="candidate_signals_strength_range"),
        Index("candidate_signals_org_run_idx", "organization_id", "detection_run_id"),
    )

    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    detection_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    signal_key: Mapped[str] = mapped_column(
        Text,
        ForeignKey("detection_signal_definitions.key", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_kind: Mapped[RuleKind] = mapped_column(RULE_KIND, nullable=False)
    outcome: Mapped[SignalOutcome] = mapped_column(SIGNAL_OUTCOME, nullable=False)
    strength: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, server_default=text("1")
    )
    raw_value: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    weight_applied: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    contribution: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class CandidateScoreHistory(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "candidate_score_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="candidate_score_history_candidate_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "detection_run_id"],
            ["detection_runs.organization_id", "detection_runs.id"],
            name="candidate_score_history_run_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="candidate_score_history_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "candidate_id",
            "detection_run_id",
            name="candidate_score_history_candidate_run_key",
        ),
        CheckConstraint(
            "normalized_score BETWEEN 0 AND 100",
            name="candidate_score_history_normalized_range",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    detection_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    raw_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    normalized_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    score_band: Mapped[ScoreBand] = mapped_column(SCORE_BAND, nullable=False)
    is_suppressed: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )


class ReworkCategory(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "rework_categories"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="rework_categories_org_id_key"),
        UniqueConstraint("organization_id", "key", name="rework_categories_org_key"),
        CheckConstraint("sort_order >= 0", name="rework_categories_sort_nonnegative"),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[CategoryOutcome] = mapped_column(CATEGORY_OUTCOME, nullable=False)
    counts_toward_cost: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    is_system_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    color: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))


class RootCause(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "root_causes"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="root_causes_org_id_key"),
        UniqueConstraint("organization_id", "key", name="root_causes_org_key"),
        ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["root_causes.organization_id", "root_causes.id"],
            name="root_causes_parent_fkey",
            ondelete="RESTRICT",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="root_causes_not_self"),
        CheckConstraint("sort_order >= 0", name="root_causes_sort_nonnegative"),
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    is_system_default: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))


class ReworkReview(Base, PrimaryKeyMixin, TenantMixin):
    __tablename__ = "rework_reviews"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="rework_reviews_org_id_key"),
        ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="rework_reviews_candidate_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["rework_categories.organization_id", "rework_categories.id"],
            name="rework_reviews_category_fkey",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "root_cause_id"],
            ["root_causes.organization_id", "root_causes.id"],
            name="rework_reviews_root_cause_fkey",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rule_set_id_at_review"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="rework_reviews_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "superseded_by_review_id"],
            ["rework_reviews.organization_id", "rework_reviews.id"],
            name="rework_reviews_superseded_by_fkey",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index(
            "rework_reviews_current_candidate_key",
            "candidate_id",
            unique=True,
            postgresql_where=text("superseded_by_review_id IS NULL"),
        ),
        Index("rework_reviews_org_decided_idx", "organization_id", text("decided_at DESC")),
        Index("rework_reviews_org_category_idx", "organization_id", "category_id"),
        Index("rework_reviews_org_reviewer_idx", "organization_id", "reviewed_by_user_id"),
        CheckConstraint(
            "decision <> 'confirmed' OR category_id IS NOT NULL",
            name="rework_reviews_confirmed_category_required",
        ),
        CheckConstraint(
            "decision = 'confirmed' OR root_cause_id IS NULL",
            name="rework_reviews_root_cause_confirmed_only",
        ),
        CheckConstraint(
            "score_at_review IS NULL OR score_at_review BETWEEN 0 AND 100",
            name="rework_reviews_score_range",
        ),
    )

    candidate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    decision: Mapped[ReviewDecision] = mapped_column(REVIEW_DECISION, nullable=False)
    category_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    root_cause_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    score_at_review: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    rule_set_id_at_review: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    decided_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    superseded_by_review_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
