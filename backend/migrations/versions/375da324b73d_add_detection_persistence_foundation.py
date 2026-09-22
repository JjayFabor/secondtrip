"""add detection persistence foundation

Revision ID: 375da324b73d
Revises: d17f4a2c8e63
Create Date: 2026-09-22 15:24:15.225303
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.rls_helpers import disable_rls, enable_rls

revision: str = "375da324b73d"
down_revision: str | None = "d17f4a2c8e63"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

SIGNAL_VALUE_TYPE_ENUM = postgresql.ENUM(
    "boolean", "numeric", "ratio", "categorical", name="signal_value_type", create_type=False
)
RULE_KIND_ENUM = postgresql.ENUM(
    "additive", "multiplier", "gate", "veto", name="rule_kind", create_type=False
)
DETECTION_TRIGGER_ENUM = postgresql.ENUM(
    "import_completed",
    "rules_changed",
    "manual",
    "scheduled",
    "embeddings_ready",
    name="detection_trigger",
    create_type=False,
)
DETECTION_RUN_STATUS_ENUM = postgresql.ENUM(
    "queued",
    "running",
    "completed",
    "failed",
    "cancelled",
    name="run_status",
    create_type=False,
)
SCORE_BAND_ENUM = postgresql.ENUM("low", "medium", "high", name="score_band", create_type=False)
SIMILARITY_STATE_ENUM = postgresql.ENUM(
    "pending",
    "computed",
    "unavailable",
    "not_applicable",
    name="similarity_state",
    create_type=False,
)
CANDIDATE_WORKFLOW_STATUS_ENUM = postgresql.ENUM(
    "open",
    "in_review",
    "reviewed",
    "dismissed",
    name="candidate_workflow_status",
    create_type=False,
)
SIGNAL_OUTCOME_ENUM = postgresql.ENUM(
    "matched",
    "not_matched",
    "not_evaluable",
    name="signal_outcome",
    create_type=False,
)
ENUM_TYPES = (
    SIGNAL_VALUE_TYPE_ENUM,
    RULE_KIND_ENUM,
    DETECTION_TRIGGER_ENUM,
    DETECTION_RUN_STATUS_ENUM,
    SCORE_BAND_ENUM,
    SIMILARITY_STATE_ENUM,
    CANDIDATE_WORKFLOW_STATUS_ENUM,
    SIGNAL_OUTCOME_ENUM,
)
TENANT_TABLES = (
    "detection_rule_sets",
    "detection_rules",
    "detection_runs",
    "rework_candidates",
    "candidate_score_history",
    "candidate_signals",
)


def _seed_signal_catalogue() -> None:
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO detection_signal_definitions
            (key, label, description, value_type, default_weight, default_params,
             supported_kinds, requires_embeddings)
        VALUES
            ('same_customer', 'Same customer',
             'Both visits belong to the same customer.', 'boolean', 20, '{}',
             ARRAY['additive'], false),
            ('same_location', 'Same location',
             'Both visits occurred at the same service location.', 'boolean', 15, '{}',
             ARRAY['additive'], false),
            ('same_equipment', 'Same equipment',
             'Both visits reference the same equipment record.', 'boolean', 30, '{}',
             ARRAY['additive'], false),
            ('days_between', 'Days between visits',
             'Scores the org-local calendar-day interval using configurable bands.',
             'numeric', 25,
             '{"bands":[[0,1,"0.70"],[2,7,"1.00"],[8,14,"0.80"],'
             '[15,30,"0.50"],[31,90,"0.25"]]}', ARRAY['additive'], false),
            ('same_service_category', 'Same service category',
             'Both visits share the same normalized service category.', 'boolean', 10, '{}',
             ARRAY['additive'], false),
            ('zero_value_followup', 'Zero-value follow-up',
             'The follow-up visit has an explicitly recorded zero revenue amount.',
             'boolean', 25, '{}', ARRAY['additive'], false),
            ('low_value_followup', 'Low-value follow-up',
             'The follow-up revenue is below the configured share of the prior visit.',
             'ratio', 10, '{"maximum_ratio":"0.20"}', ARRAY['additive'], false),
            ('warranty_marker', 'Warranty marker',
             'The follow-up visit is explicitly marked as warranty work.', 'boolean', 25, '{}',
             ARRAY['additive'], false),
            ('within_equipment_warranty', 'Within equipment warranty',
             'The follow-up occurred on or before the equipment warranty expiry date.',
             'boolean', 10, '{}', ARRAY['additive'], false),
            ('same_technician', 'Same technician',
             'The same technician is assigned to both visits.', 'boolean', 5, '{}',
             ARRAY['additive'], false),
            ('repeat_part_code', 'Repeated part code',
             'A part code appears on both visits.', 'categorical', 20, '{}',
             ARRAY['additive'], false),
            ('recurrence_density', 'Recurrence density',
             'At least the configured number of related visits occurs inside the window.',
             'numeric', 10, '{"minimum_visits":3}', ARRAY['additive'], false),
            ('description_similarity', 'Description similarity',
             'The two problem descriptions meet the configured semantic similarity threshold.',
             'ratio', 20, '{}', ARRAY['additive'], true),
            ('scheduled_maintenance', 'Scheduled maintenance',
             'The follow-up category belongs to the organization''s maintenance set.',
             'boolean', 0, '{}', ARRAY['veto'], false),
            ('planned_multivisit', 'Planned multi-visit work',
             'The prior visit is identified as part of planned multi-visit work.',
             'boolean', 0, '{}', ARRAY['veto'], false)
        """
    )


def _backfill_default_rule_sets() -> None:
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO detection_rule_sets
            (id, organization_id, version_number, name, is_active, window_days,
             min_score_to_surface, min_score_for_ai, similarity_threshold,
             max_followups_per_job, created_by_user_id)
        SELECT gen_random_uuid(), organizations.id, 1, 'SecondTrip defaults', true, 30,
               40, 65, 0.780, 25, organizations.created_by_user_id
        FROM organizations
        WHERE organizations.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM detection_rule_sets
              WHERE detection_rule_sets.organization_id = organizations.id
          )
        """
    )
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO detection_rules
            (id, organization_id, rule_set_id, signal_key, kind, weight, params,
             is_enabled, sort_order)
        SELECT gen_random_uuid(), rule_sets.organization_id, rule_sets.id, definitions.key,
               CASE WHEN definitions.key IN ('scheduled_maintenance', 'planned_multivisit')
                    THEN 'veto'::rule_kind ELSE 'additive'::rule_kind END,
               definitions.default_weight, definitions.default_params, true,
               CASE definitions.key
                   WHEN 'same_customer' THEN 10 WHEN 'same_location' THEN 20
                   WHEN 'same_equipment' THEN 30 WHEN 'days_between' THEN 40
                   WHEN 'same_service_category' THEN 50 WHEN 'zero_value_followup' THEN 60
                   WHEN 'low_value_followup' THEN 70 WHEN 'warranty_marker' THEN 80
                   WHEN 'within_equipment_warranty' THEN 90 WHEN 'same_technician' THEN 100
                   WHEN 'repeat_part_code' THEN 110 WHEN 'recurrence_density' THEN 120
                   WHEN 'description_similarity' THEN 130
                   WHEN 'scheduled_maintenance' THEN 140 ELSE 150
               END
        FROM detection_rule_sets AS rule_sets
        CROSS JOIN detection_signal_definitions AS definitions
        WHERE rule_sets.version_number = 1
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ENUM_TYPES:
        enum_type.create(bind, checkfirst=True)
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "detection_signal_definitions",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "value_type",
            SIGNAL_VALUE_TYPE_ENUM,
            nullable=False,
        ),
        sa.Column("default_weight", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column(
            "default_params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("supported_kinds", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "requires_embeddings", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "detection_rule_sets",
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("window_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column(
            "min_score_to_surface",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("40"),
            nullable=False,
        ),
        sa.Column(
            "min_score_for_ai",
            sa.Numeric(precision=5, scale=2),
            server_default=sa.text("65"),
            nullable=False,
        ),
        sa.Column(
            "similarity_threshold",
            sa.Numeric(precision=4, scale=3),
            server_default=sa.text("0.780"),
            nullable=False,
        ),
        sa.Column(
            "max_followups_per_job", sa.Integer(), server_default=sa.text("25"), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "max_followups_per_job > 0", name="detection_rule_sets_followups_positive"
        ),
        sa.CheckConstraint(
            "min_score_for_ai BETWEEN 0 AND 100", name="detection_rule_sets_ai_score_range"
        ),
        sa.CheckConstraint(
            "min_score_to_surface BETWEEN 0 AND 100", name="detection_rule_sets_surface_score_range"
        ),
        sa.CheckConstraint(
            "similarity_threshold BETWEEN 0 AND 1", name="detection_rule_sets_similarity_range"
        ),
        sa.CheckConstraint("version_number > 0", name="detection_rule_sets_version_positive"),
        sa.CheckConstraint("window_days > 0", name="detection_rule_sets_window_positive"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="detection_rule_sets_org_id_key"),
        sa.UniqueConstraint(
            "organization_id", "version_number", name="detection_rule_sets_org_version_key"
        ),
    )
    op.create_index(
        "detection_rule_sets_org_active_key",
        "detection_rule_sets",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        op.f("ix_detection_rule_sets_organization_id"),
        "detection_rule_sets",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "detection_rules",
        sa.Column("rule_set_id", sa.UUID(), nullable=False),
        sa.Column("signal_key", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            RULE_KIND_ENUM,
            nullable=False,
        ),
        sa.Column(
            "weight", sa.Numeric(precision=8, scale=2), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("weight >= 0", name="detection_rules_weight_nonnegative"),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="detection_rules_rule_set_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["signal_key"], ["detection_signal_definitions.key"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("rule_set_id", "signal_key", name="detection_rules_set_signal_key"),
    )
    op.create_index(
        op.f("ix_detection_rules_organization_id"),
        "detection_rules",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "detection_runs",
        sa.Column("rule_set_id", sa.UUID(), nullable=False),
        sa.Column(
            "trigger",
            DETECTION_TRIGGER_ENUM,
            nullable=False,
        ),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "status",
            DETECTION_RUN_STATUS_ENUM,
            server_default="queued",
            nullable=False,
        ),
        sa.Column("pairs_evaluated", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidates_created", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("candidates_updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "candidates_suppressed", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column("background_job_id", sa.UUID(), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("candidates_created >= 0", name="detection_runs_created_nonnegative"),
        sa.CheckConstraint(
            "candidates_suppressed >= 0", name="detection_runs_suppressed_nonnegative"
        ),
        sa.CheckConstraint("candidates_updated >= 0", name="detection_runs_updated_nonnegative"),
        sa.CheckConstraint("pairs_evaluated >= 0", name="detection_runs_pairs_nonnegative"),
        sa.ForeignKeyConstraint(["background_job_id"], ["background_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="detection_runs_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="detection_runs_org_id_key"),
    )
    op.create_index(
        "detection_runs_org_started_idx",
        "detection_runs",
        ["organization_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        op.f("ix_detection_runs_organization_id"),
        "detection_runs",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "rework_candidates",
        sa.Column("prior_job_id", sa.UUID(), nullable=False),
        sa.Column("followup_job_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=True),
        sa.Column("location_id", sa.UUID(), nullable=True),
        sa.Column("equipment_id", sa.UUID(), nullable=True),
        sa.Column("technician_prior_id", sa.UUID(), nullable=True),
        sa.Column("technician_followup_id", sa.UUID(), nullable=True),
        sa.Column("days_between", sa.Integer(), nullable=False),
        sa.Column("current_score", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("current_normalized_score", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("score_band", SCORE_BAND_ENUM, nullable=True),
        sa.Column("is_suppressed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suppressed_by_signal_key", sa.Text(), nullable=True),
        sa.Column(
            "similarity_state",
            SIMILARITY_STATE_ENUM,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("similarity_score", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column(
            "workflow_status",
            CANDIDATE_WORKFLOW_STATUS_ENUM,
            server_default="open",
            nullable=False,
        ),
        sa.Column("current_rule_set_id", sa.UUID(), nullable=True),
        sa.Column("current_detection_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "first_detected_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_evaluated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "current_normalized_score IS NULL OR current_normalized_score BETWEEN 0 AND 100",
            name="rework_candidates_normalized_score_range",
        ),
        sa.CheckConstraint("days_between >= 0", name="rework_candidates_days_nonnegative"),
        sa.CheckConstraint(
            "prior_job_id <> followup_job_id", name="rework_candidates_distinct_jobs"
        ),
        sa.CheckConstraint(
            "similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1",
            name="rework_candidates_similarity_range",
        ),
        sa.ForeignKeyConstraint(
            ["current_detection_run_id"], ["detection_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["current_rule_set_id"], ["detection_rule_sets.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "followup_job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="rework_candidates_followup_job_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "prior_job_id"],
            ["jobs.organization_id", "jobs.id"],
            name="rework_candidates_prior_job_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["suppressed_by_signal_key"], ["detection_signal_definitions.key"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="rework_candidates_org_id_key"),
        sa.UniqueConstraint(
            "organization_id",
            "prior_job_id",
            "followup_job_id",
            name="rework_candidates_org_pair_key",
        ),
    )
    op.create_index(
        op.f("ix_rework_candidates_organization_id"),
        "rework_candidates",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "rework_candidates_org_equipment_idx",
        "rework_candidates",
        ["organization_id", "equipment_id"],
        unique=False,
        postgresql_where=sa.text("equipment_id IS NOT NULL"),
    )
    op.create_index(
        "rework_candidates_org_followup_idx",
        "rework_candidates",
        ["organization_id", "followup_job_id"],
        unique=False,
    )
    op.create_index(
        "rework_candidates_org_prior_idx",
        "rework_candidates",
        ["organization_id", "prior_job_id"],
        unique=False,
    )
    op.create_index(
        "rework_candidates_org_review_queue_idx",
        "rework_candidates",
        [
            "organization_id",
            sa.literal_column("current_normalized_score DESC"),
            sa.literal_column("id DESC"),
        ],
        unique=False,
        postgresql_where=sa.text("NOT is_suppressed AND workflow_status = 'open'"),
    )
    op.create_index(
        "rework_candidates_org_run_idx",
        "rework_candidates",
        ["organization_id", "current_detection_run_id"],
        unique=False,
    )
    op.create_index(
        "rework_candidates_org_workflow_evaluated_idx",
        "rework_candidates",
        ["organization_id", "workflow_status", sa.literal_column("last_evaluated_at DESC")],
        unique=False,
    )
    op.create_table(
        "candidate_score_history",
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("detection_run_id", sa.UUID(), nullable=False),
        sa.Column("rule_set_id", sa.UUID(), nullable=False),
        sa.Column("raw_score", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("normalized_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("score_band", SCORE_BAND_ENUM, nullable=False),
        sa.Column("is_suppressed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "normalized_score BETWEEN 0 AND 100", name="candidate_score_history_normalized_range"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="candidate_score_history_candidate_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "detection_run_id"],
            ["detection_runs.organization_id", "detection_runs.id"],
            name="candidate_score_history_run_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_set_id"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="candidate_score_history_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id", "detection_run_id", name="candidate_score_history_candidate_run_key"
        ),
    )
    op.create_index(
        op.f("ix_candidate_score_history_organization_id"),
        "candidate_score_history",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "candidate_signals",
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("detection_run_id", sa.UUID(), nullable=False),
        sa.Column("signal_key", sa.Text(), nullable=False),
        sa.Column(
            "rule_kind",
            RULE_KIND_ENUM,
            nullable=False,
        ),
        sa.Column(
            "outcome",
            SIGNAL_OUTCOME_ENUM,
            nullable=False,
        ),
        sa.Column(
            "strength",
            sa.Numeric(precision=5, scale=4),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("raw_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weight_applied", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("contribution", sa.Numeric(precision=8, scale=2), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("strength BETWEEN 0 AND 1", name="candidate_signals_strength_range"),
        sa.ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="candidate_signals_candidate_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "detection_run_id"],
            ["detection_runs.organization_id", "detection_runs.id"],
            name="candidate_signals_run_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["signal_key"], ["detection_signal_definitions.key"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_id",
            "detection_run_id",
            "signal_key",
            name="candidate_signals_candidate_run_signal_key",
        ),
    )
    op.create_index(
        "candidate_signals_org_run_idx",
        "candidate_signals",
        ["organization_id", "detection_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_signals_organization_id"),
        "candidate_signals",
        ["organization_id"],
        unique=False,
    )
    _seed_signal_catalogue()
    _backfill_default_rule_sets()
    for table_name in TENANT_TABLES:
        enable_rls(table_name)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    for table_name in reversed(TENANT_TABLES):
        disable_rls(table_name)
    op.drop_index(op.f("ix_candidate_signals_organization_id"), table_name="candidate_signals")
    op.drop_index("candidate_signals_org_run_idx", table_name="candidate_signals")
    op.drop_table("candidate_signals")
    op.drop_index(
        op.f("ix_candidate_score_history_organization_id"), table_name="candidate_score_history"
    )
    op.drop_table("candidate_score_history")
    op.drop_index("rework_candidates_org_workflow_evaluated_idx", table_name="rework_candidates")
    op.drop_index("rework_candidates_org_run_idx", table_name="rework_candidates")
    op.drop_index(
        "rework_candidates_org_review_queue_idx",
        table_name="rework_candidates",
        postgresql_where=sa.text("NOT is_suppressed AND workflow_status = 'open'"),
    )
    op.drop_index("rework_candidates_org_prior_idx", table_name="rework_candidates")
    op.drop_index("rework_candidates_org_followup_idx", table_name="rework_candidates")
    op.drop_index(
        "rework_candidates_org_equipment_idx",
        table_name="rework_candidates",
        postgresql_where=sa.text("equipment_id IS NOT NULL"),
    )
    op.drop_index(op.f("ix_rework_candidates_organization_id"), table_name="rework_candidates")
    op.drop_table("rework_candidates")
    op.drop_index(op.f("ix_detection_runs_organization_id"), table_name="detection_runs")
    op.drop_index("detection_runs_org_started_idx", table_name="detection_runs")
    op.drop_table("detection_runs")
    op.drop_index(op.f("ix_detection_rules_organization_id"), table_name="detection_rules")
    op.drop_table("detection_rules")
    op.drop_index(op.f("ix_detection_rule_sets_organization_id"), table_name="detection_rule_sets")
    op.drop_index(
        "detection_rule_sets_org_active_key",
        table_name="detection_rule_sets",
        postgresql_where=sa.text("is_active"),
    )
    op.drop_table("detection_rule_sets")
    op.drop_table("detection_signal_definitions")
    bind = op.get_bind()
    for enum_type in reversed(ENUM_TYPES):
        enum_type.drop(bind, checkfirst=True)
    # ### end Alembic commands ###
