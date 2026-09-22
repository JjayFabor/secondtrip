"""add review truth foundation

Revision ID: a6d9f31c7b42
Revises: f4a2c8e63b10
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.rls_helpers import disable_rls, enable_rls

revision: str = "a6d9f31c7b42"
down_revision: str | None = "f4a2c8e63b10"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

CATEGORY_OUTCOME_ENUM = postgresql.ENUM(
    "rework",
    "not_rework",
    "uncertain",
    name="category_outcome",
    create_type=False,
)
REVIEW_DECISION_ENUM = postgresql.ENUM(
    "confirmed",
    "rejected",
    "uncertain",
    name="review_decision",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    CATEGORY_OUTCOME_ENUM.create(bind, checkfirst=True)
    REVIEW_DECISION_ENUM.create(bind, checkfirst=True)

    op.create_table(
        "rework_categories",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("outcome", CATEGORY_OUTCOME_ENUM, nullable=False),
        sa.Column(
            "counts_toward_cost", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "is_system_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("color", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="rework_categories_sort_nonnegative"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="rework_categories_org_id_key"),
        sa.UniqueConstraint("organization_id", "key", name="rework_categories_org_key"),
    )
    op.create_index(
        op.f("ix_rework_categories_organization_id"),
        "rework_categories",
        ["organization_id"],
    )

    op.create_table(
        "root_causes",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column(
            "is_system_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="root_causes_not_self"),
        sa.CheckConstraint("sort_order >= 0", name="root_causes_sort_nonnegative"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["root_causes.organization_id", "root_causes.id"],
            name="root_causes_parent_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="root_causes_org_id_key"),
        sa.UniqueConstraint("organization_id", "key", name="root_causes_org_key"),
    )
    op.create_index(op.f("ix_root_causes_organization_id"), "root_causes", ["organization_id"])

    op.create_table(
        "rework_reviews",
        sa.Column("candidate_id", sa.UUID(), nullable=False),
        sa.Column("decision", REVIEW_DECISION_ENUM, nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=True),
        sa.Column("root_cause_id", sa.UUID(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.UUID(), nullable=False),
        sa.Column("score_at_review", sa.Numeric(5, 2), nullable=True),
        sa.Column("rule_set_id_at_review", sa.UUID(), nullable=True),
        sa.Column(
            "decided_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("superseded_by_review_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "decision <> 'confirmed' OR category_id IS NOT NULL",
            name="rework_reviews_confirmed_category_required",
        ),
        sa.CheckConstraint(
            "decision = 'confirmed' OR root_cause_id IS NULL",
            name="rework_reviews_root_cause_confirmed_only",
        ),
        sa.CheckConstraint(
            "score_at_review IS NULL OR score_at_review BETWEEN 0 AND 100",
            name="rework_reviews_score_range",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "candidate_id"],
            ["rework_candidates.organization_id", "rework_candidates.id"],
            name="rework_reviews_candidate_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "category_id"],
            ["rework_categories.organization_id", "rework_categories.id"],
            name="rework_reviews_category_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "root_cause_id"],
            ["root_causes.organization_id", "root_causes.id"],
            name="rework_reviews_root_cause_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rule_set_id_at_review"],
            ["detection_rule_sets.organization_id", "detection_rule_sets.id"],
            name="rework_reviews_rule_set_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "superseded_by_review_id"],
            ["rework_reviews.organization_id", "rework_reviews.id"],
            name="rework_reviews_superseded_by_fkey",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="rework_reviews_org_id_key"),
    )
    op.create_index(
        op.f("ix_rework_reviews_organization_id"), "rework_reviews", ["organization_id"]
    )
    op.create_index(
        "rework_reviews_current_candidate_key",
        "rework_reviews",
        ["candidate_id"],
        unique=True,
        postgresql_where=sa.text("superseded_by_review_id IS NULL"),
    )
    op.create_index(
        "rework_reviews_org_decided_idx",
        "rework_reviews",
        ["organization_id", sa.literal_column("decided_at DESC")],
    )
    op.create_index(
        "rework_reviews_org_category_idx",
        "rework_reviews",
        ["organization_id", "category_id"],
    )
    op.create_index(
        "rework_reviews_org_reviewer_idx",
        "rework_reviews",
        ["organization_id", "reviewed_by_user_id"],
    )

    for table_name in ("rework_categories", "root_causes", "rework_reviews"):
        enable_rls(table_name)
    op.execute("REVOKE UPDATE, DELETE ON rework_reviews FROM secondtrip_app")
    op.execute(
        "GRANT UPDATE (superseded_by_review_id) ON rework_reviews TO secondtrip_app"
    )

    _seed_existing_organizations()


def _seed_existing_organizations() -> None:
    op.execute(
        """
        INSERT INTO rework_categories
            (id, organization_id, key, label, outcome, counts_toward_cost,
             is_system_default, sort_order)
        SELECT gen_random_uuid(), organizations.id, defaults.key, defaults.label,
               defaults.outcome::category_outcome, defaults.counts_toward_cost, true,
               defaults.sort_order
        FROM organizations
        CROSS JOIN (VALUES
            ('confirmed_callback', 'Confirmed callback', 'rework', true, 10),
            ('warranty', 'Warranty', 'rework', true, 11),
            ('workmanship', 'Workmanship', 'rework', true, 12),
            ('misdiagnosis', 'Misdiagnosis', 'rework', true, 13),
            ('failed_part', 'Failed part', 'rework', true, 14),
            ('incomplete_repair', 'Incomplete repair', 'rework', true, 15),
            ('scheduled_followup', 'Scheduled follow-up', 'not_rework', false, 16),
            ('customer_caused', 'Customer caused', 'not_rework', false, 17),
            ('unrelated', 'Unrelated', 'not_rework', false, 18),
            ('unsure', 'Unsure', 'uncertain', false, 19)
        ) AS defaults(key, label, outcome, counts_toward_cost, sort_order)
        ON CONFLICT (organization_id, key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO root_causes
            (id, organization_id, key, label, is_system_default, sort_order)
        SELECT gen_random_uuid(), organizations.id, defaults.key, defaults.label, true,
               defaults.sort_order
        FROM organizations
        CROSS JOIN (VALUES
            ('workmanship', 'Workmanship', 10),
            ('diagnosis', 'Diagnosis', 11),
            ('part_quality', 'Part quality', 12),
            ('parts_availability', 'Parts availability', 13),
            ('access_or_scheduling', 'Access or scheduling', 14),
            ('customer_behaviour', 'Customer behaviour', 15),
            ('system_design', 'System design', 16),
            ('documentation', 'Documentation', 17),
            ('other', 'Other', 18)
        ) AS defaults(key, label, sort_order)
        ON CONFLICT (organization_id, key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON rework_reviews TO secondtrip_app")
    for table_name in ("rework_reviews", "root_causes", "rework_categories"):
        disable_rls(table_name)

    op.drop_index("rework_reviews_org_reviewer_idx", table_name="rework_reviews")
    op.drop_index("rework_reviews_org_category_idx", table_name="rework_reviews")
    op.drop_index("rework_reviews_org_decided_idx", table_name="rework_reviews")
    op.drop_index("rework_reviews_current_candidate_key", table_name="rework_reviews")
    op.drop_index(op.f("ix_rework_reviews_organization_id"), table_name="rework_reviews")
    op.drop_table("rework_reviews")
    op.drop_index(op.f("ix_root_causes_organization_id"), table_name="root_causes")
    op.drop_table("root_causes")
    op.drop_index(op.f("ix_rework_categories_organization_id"), table_name="rework_categories")
    op.drop_table("rework_categories")
    REVIEW_DECISION_ENUM.drop(op.get_bind(), checkfirst=True)
    CATEGORY_OUTCOME_ENUM.drop(op.get_bind(), checkfirst=True)
