"""Human review taxonomy and append-only review writes."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.ids import new_id
from app.modules.audit.schemas import ActorType
from app.modules.audit.service import record as record_audit_event
from app.modules.detection.models import (
    ReworkCandidate,
    ReworkCategory,
    ReworkReview,
    RootCause,
)
from app.modules.detection.schemas import (
    CandidateWorkflowStatus,
    CategoryOutcome,
    ReviewDecision,
)


@dataclass(frozen=True, slots=True)
class CategoryDefault:
    key: str
    label: str
    outcome: CategoryOutcome
    counts_toward_cost: bool


CATEGORY_DEFAULTS = (
    CategoryDefault("confirmed_callback", "Confirmed callback", CategoryOutcome.REWORK, True),
    CategoryDefault("warranty", "Warranty", CategoryOutcome.REWORK, True),
    CategoryDefault("workmanship", "Workmanship", CategoryOutcome.REWORK, True),
    CategoryDefault("misdiagnosis", "Misdiagnosis", CategoryOutcome.REWORK, True),
    CategoryDefault("failed_part", "Failed part", CategoryOutcome.REWORK, True),
    CategoryDefault("incomplete_repair", "Incomplete repair", CategoryOutcome.REWORK, True),
    CategoryDefault("scheduled_followup", "Scheduled follow-up", CategoryOutcome.NOT_REWORK, False),
    CategoryDefault("customer_caused", "Customer caused", CategoryOutcome.NOT_REWORK, False),
    CategoryDefault("unrelated", "Unrelated", CategoryOutcome.NOT_REWORK, False),
    CategoryDefault("unsure", "Unsure", CategoryOutcome.UNCERTAIN, False),
)

ROOT_CAUSE_DEFAULTS = (
    ("workmanship", "Workmanship"),
    ("diagnosis", "Diagnosis"),
    ("part_quality", "Part quality"),
    ("parts_availability", "Parts availability"),
    ("access_or_scheduling", "Access or scheduling"),
    ("customer_behaviour", "Customer behaviour"),
    ("system_design", "System design"),
    ("documentation", "Documentation"),
    ("other", "Other"),
)


async def ensure_review_taxonomy(
    session: AsyncSession, *, organization_id: UUID
) -> tuple[list[ReworkCategory], list[RootCause]]:
    """Insert any missing system defaults without changing tenant customizations."""

    categories = list(
        (
            await session.execute(
                select(ReworkCategory).where(ReworkCategory.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    category_keys = {category.key for category in categories}
    for sort_order, default in enumerate(CATEGORY_DEFAULTS, start=10):
        if default.key in category_keys:
            continue
        category = ReworkCategory(
            organization_id=organization_id,
            key=default.key,
            label=default.label,
            outcome=default.outcome,
            counts_toward_cost=default.counts_toward_cost,
            is_system_default=True,
            sort_order=sort_order,
        )
        session.add(category)
        categories.append(category)

    root_causes = list(
        (
            await session.execute(
                select(RootCause).where(RootCause.organization_id == organization_id)
            )
        )
        .scalars()
        .all()
    )
    root_cause_keys = {root_cause.key for root_cause in root_causes}
    for sort_order, (key, label) in enumerate(ROOT_CAUSE_DEFAULTS, start=10):
        if key in root_cause_keys:
            continue
        root_cause = RootCause(
            organization_id=organization_id,
            key=key,
            label=label,
            is_system_default=True,
            sort_order=sort_order,
        )
        session.add(root_cause)
        root_causes.append(root_cause)

    await session.flush()
    return categories, root_causes


async def list_review_categories(
    session: AsyncSession, *, organization_id: UUID
) -> list[ReworkCategory]:
    return list(
        (
            await session.execute(
                select(ReworkCategory)
                .where(ReworkCategory.organization_id == organization_id)
                .order_by(ReworkCategory.sort_order, ReworkCategory.label, ReworkCategory.id)
            )
        )
        .scalars()
        .all()
    )


async def list_root_causes(session: AsyncSession, *, organization_id: UUID) -> list[RootCause]:
    return list(
        (
            await session.execute(
                select(RootCause)
                .where(RootCause.organization_id == organization_id)
                .order_by(RootCause.sort_order, RootCause.label, RootCause.id)
            )
        )
        .scalars()
        .all()
    )


async def list_review_history(
    session: AsyncSession,
    *,
    organization_id: UUID,
    candidate_id: UUID,
) -> list[ReworkReview]:
    candidate_exists = await session.scalar(
        select(ReworkCandidate.id).where(
            ReworkCandidate.organization_id == organization_id,
            ReworkCandidate.id == candidate_id,
        )
    )
    if candidate_exists is None:
        raise NotFoundError("Candidate not found.")

    return list(
        (
            await session.execute(
                select(ReworkReview)
                .where(
                    ReworkReview.organization_id == organization_id,
                    ReworkReview.candidate_id == candidate_id,
                )
                .order_by(ReworkReview.decided_at.desc(), ReworkReview.id.desc())
            )
        )
        .scalars()
        .all()
    )


async def record_review(
    session: AsyncSession,
    *,
    organization_id: UUID,
    candidate_id: UUID,
    decision: ReviewDecision,
    category_id: UUID | None,
    root_cause_id: UUID | None,
    note: str | None,
    reviewed_by_user_id: UUID,
    reviewer_label: str,
    request_id: str | None = None,
) -> ReworkReview:
    """Append a review, superseding the prior current review atomically."""

    candidate = await session.scalar(
        select(ReworkCandidate)
        .where(
            ReworkCandidate.organization_id == organization_id,
            ReworkCandidate.id == candidate_id,
        )
        .with_for_update()
    )
    if candidate is None:
        raise NotFoundError("Candidate not found.")
    if candidate.is_suppressed:
        raise ConflictError("Unsuppress the candidate before reviewing it.")

    category = await _resolve_category(session, organization_id, category_id)
    root_cause = await _resolve_root_cause(session, organization_id, root_cause_id)
    _validate_review_choice(decision, category, root_cause)

    current = await session.scalar(
        select(ReworkReview)
        .where(
            ReworkReview.organization_id == organization_id,
            ReworkReview.candidate_id == candidate_id,
            ReworkReview.superseded_by_review_id.is_(None),
        )
        .with_for_update()
    )
    review = ReworkReview(
        id=new_id(),
        organization_id=organization_id,
        candidate_id=candidate_id,
        decision=decision,
        category_id=category.id if category is not None else None,
        root_cause_id=root_cause.id if root_cause is not None else None,
        note=note.strip() if note and note.strip() else None,
        reviewed_by_user_id=reviewed_by_user_id,
        score_at_review=candidate.current_normalized_score,
        rule_set_id_at_review=candidate.current_rule_set_id,
    )
    if current is not None:
        await session.execute(
            update(ReworkReview)
            .where(
                ReworkReview.id == current.id,
                ReworkReview.superseded_by_review_id.is_(None),
            )
            .values(superseded_by_review_id=review.id)
        )
    session.add(review)
    candidate.workflow_status = CandidateWorkflowStatus.REVIEWED
    await record_audit_event(
        session,
        organization_id=organization_id,
        action="candidate.reviewed",
        summary=f"Candidate review recorded as {decision.value}.",
        actor_type=ActorType.USER,
        actor_user_id=reviewed_by_user_id,
        actor_label=reviewer_label,
        resource_type="rework_review",
        resource_id=review.id,
        changes={
            "decision": decision.value,
            "category_id": str(review.category_id) if review.category_id else None,
            "root_cause_id": str(review.root_cause_id) if review.root_cause_id else None,
            "supersedes_review_id": str(current.id) if current else None,
        },
        request_id=request_id,
    )
    await session.flush()
    return review


async def _resolve_category(
    session: AsyncSession, organization_id: UUID, category_id: UUID | None
) -> ReworkCategory | None:
    if category_id is None:
        return None
    category = await session.scalar(
        select(ReworkCategory).where(
            ReworkCategory.organization_id == organization_id,
            ReworkCategory.id == category_id,
            ReworkCategory.is_active.is_(True),
        )
    )
    if category is None:
        raise NotFoundError("Category not found.")
    return category


async def _resolve_root_cause(
    session: AsyncSession, organization_id: UUID, root_cause_id: UUID | None
) -> RootCause | None:
    if root_cause_id is None:
        return None
    root_cause = await session.scalar(
        select(RootCause).where(
            RootCause.organization_id == organization_id,
            RootCause.id == root_cause_id,
            RootCause.is_active.is_(True),
        )
    )
    if root_cause is None:
        raise NotFoundError("Root cause not found.")
    return root_cause


def _validate_review_choice(
    decision: ReviewDecision,
    category: ReworkCategory | None,
    root_cause: RootCause | None,
) -> None:
    expected_outcome = {
        ReviewDecision.CONFIRMED: CategoryOutcome.REWORK,
        ReviewDecision.REJECTED: CategoryOutcome.NOT_REWORK,
        ReviewDecision.UNCERTAIN: CategoryOutcome.UNCERTAIN,
    }[decision]
    if decision is ReviewDecision.CONFIRMED and category is None:
        raise ConflictError("Confirmed reviews require a category.")
    if category is not None and category.outcome is not expected_outcome:
        raise ConflictError("The category outcome does not match the review decision.")
    if root_cause is not None and decision is not ReviewDecision.CONFIRMED:
        raise ConflictError("Only confirmed reviews can have a root cause.")
