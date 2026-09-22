"""remove deferred AI and embedding surface

Revision ID: f4a2c8e63b10
Revises: e8b7c6d5a4f3
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a2c8e63b10"
down_revision: str | None = "e8b7c6d5a4f3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _replace_detection_trigger(*values: str) -> None:
    op.alter_column(
        "detection_runs",
        "trigger",
        type_=sa.Text(),
        postgresql_using="trigger::text",
    )
    op.execute("DROP TYPE detection_trigger")
    quoted_values = ", ".join(f"'{value}'" for value in values)
    op.execute(f"CREATE TYPE detection_trigger AS ENUM ({quoted_values})")
    op.alter_column(
        "detection_runs",
        "trigger",
        type_=postgresql.ENUM(*values, name="detection_trigger", create_type=False),
        postgresql_using="trigger::detection_trigger",
    )


def upgrade() -> None:
    # Derived evidence can be recomputed. Remove it before deleting its catalogue entry.
    op.execute("DELETE FROM candidate_signals WHERE signal_key = 'description_similarity'")
    op.execute("DELETE FROM detection_rules WHERE signal_key = 'description_similarity'")
    op.execute("DELETE FROM detection_signal_definitions WHERE key = 'description_similarity'")

    op.execute(
        "DELETE FROM organization_entitlement_overrides "
        "WHERE entitlement_key IN ('ai_analyses', 'ai_spend_cents', 'embeddings_enabled')"
    )
    op.execute(
        "DELETE FROM plan_entitlements "
        "WHERE entitlement_key IN ('ai_analyses', 'ai_spend_cents', 'embeddings_enabled')"
    )

    op.drop_index("jobs_org_embedding_hash_idx", table_name="jobs")
    op.drop_column("jobs", "embedding_content_hash")

    op.drop_constraint(
        "rework_candidates_similarity_range", "rework_candidates", type_="check"
    )
    op.drop_column("rework_candidates", "similarity_score")
    op.drop_column("rework_candidates", "similarity_state")
    op.execute("DROP TYPE similarity_state")

    op.drop_constraint(
        "detection_rule_sets_ai_score_range", "detection_rule_sets", type_="check"
    )
    op.drop_constraint(
        "detection_rule_sets_similarity_range", "detection_rule_sets", type_="check"
    )
    op.drop_column("detection_rule_sets", "min_score_for_ai")
    op.drop_column("detection_rule_sets", "similarity_threshold")
    op.drop_column("detection_signal_definitions", "requires_embeddings")

    op.execute(
        "UPDATE detection_runs SET trigger = 'manual' WHERE trigger = 'embeddings_ready'"
    )
    _replace_detection_trigger(
        "import_completed",
        "rules_changed",
        "manual",
        "scheduled",
    )


def downgrade() -> None:
    _replace_detection_trigger(
        "import_completed",
        "rules_changed",
        "manual",
        "scheduled",
        "embeddings_ready",
    )

    op.add_column(
        "detection_signal_definitions",
        sa.Column(
            "requires_embeddings",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "detection_rule_sets",
        sa.Column(
            "similarity_threshold",
            sa.Numeric(4, 3),
            nullable=False,
            server_default=sa.text("0.780"),
        ),
    )
    op.add_column(
        "detection_rule_sets",
        sa.Column(
            "min_score_for_ai",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("65"),
        ),
    )
    op.create_check_constraint(
        "detection_rule_sets_similarity_range",
        "detection_rule_sets",
        "similarity_threshold BETWEEN 0 AND 1",
    )
    op.create_check_constraint(
        "detection_rule_sets_ai_score_range",
        "detection_rule_sets",
        "min_score_for_ai BETWEEN 0 AND 100",
    )

    similarity_state = postgresql.ENUM(
        "pending",
        "computed",
        "unavailable",
        "not_applicable",
        name="similarity_state",
    )
    similarity_state.create(op.get_bind())
    op.add_column(
        "rework_candidates",
        sa.Column(
            "similarity_state",
            similarity_state,
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "rework_candidates",
        sa.Column("similarity_score", sa.Numeric(4, 3), nullable=True),
    )
    op.create_check_constraint(
        "rework_candidates_similarity_range",
        "rework_candidates",
        "similarity_score IS NULL OR similarity_score BETWEEN 0 AND 1",
    )

    op.add_column("jobs", sa.Column("embedding_content_hash", sa.LargeBinary(), nullable=True))
    op.create_index(
        "jobs_org_embedding_hash_idx",
        "jobs",
        ["organization_id", "embedding_content_hash"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.execute(
        """
        INSERT INTO detection_signal_definitions
            (key, label, description, value_type, default_weight, default_params,
             supported_kinds, requires_embeddings)
        VALUES
            ('description_similarity', 'Description similarity',
             'The two problem descriptions meet the configured semantic similarity threshold.',
             'ratio', 20, '{}', ARRAY['additive'], true)
        """
    )
    op.execute(
        """
        INSERT INTO detection_rules
            (id, organization_id, rule_set_id, signal_key, kind, weight, params,
             is_enabled, sort_order)
        SELECT gen_random_uuid(), organization_id, id, 'description_similarity',
               'additive', 20, '{}', true, 130
        FROM detection_rule_sets
        """
    )
    op.execute(
        """
        INSERT INTO plan_entitlements
            (plan_id, entitlement_key, limit_value, is_boolean, period)
        SELECT plans.id, seed.entitlement_key, seed.limit_value, seed.is_boolean, seed.period
        FROM plans
        JOIN (VALUES
            ('free', 'ai_analyses', 0, false, 'month'),
            ('pro', 'ai_analyses', 500, false, 'month'),
            ('business', 'ai_analyses', 5000, false, 'month'),
            ('free', 'ai_spend_cents', 0, false, 'month'),
            ('pro', 'ai_spend_cents', 500, false, 'month'),
            ('business', 'ai_spend_cents', 5000, false, 'month'),
            ('free', 'embeddings_enabled', 1, true, NULL),
            ('pro', 'embeddings_enabled', 1, true, NULL),
            ('business', 'embeddings_enabled', 1, true, NULL)
        ) AS seed(plan_key, entitlement_key, limit_value, is_boolean, period)
          ON plans.key = seed.plan_key
        """
    )
