"""Review taxonomy and append-only human review API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.errors import InvalidCursorRequestError, NotFoundError
from app.core.pagination import InvalidCursorError, clamp_limit
from app.core.permissions import Permission
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.detection.repository import CandidateRead, DetectionRepository, SignalRead
from app.modules.detection.reviews import (
    list_review_categories,
    list_review_history,
    list_root_causes,
    record_review,
)
from app.modules.detection.schemas import (
    CandidateCustomerOut,
    CandidateDetailOut,
    CandidateEquipmentOut,
    CandidateJobOut,
    CandidateListOut,
    CandidatePageOut,
    CandidateSignalOut,
    CandidateSort,
    CandidateSummaryOut,
    CandidateWorkflowStatus,
    CreateReviewRequest,
    ReworkCategoryOut,
    ReworkReviewOut,
    RootCauseOut,
    ScoreBand,
)
from app.modules.identity.deps import AuthenticatedUser, require_session
from app.modules.organizations.deps import get_tenant_session, require_permission

router = APIRouter(prefix="/orgs/{org_id}", tags=["rework"])

require_rework_read = require_permission(Permission.REWORK_READ)
require_rework_review = require_permission(Permission.REWORK_REVIEW)


def _signal_out(read: SignalRead) -> CandidateSignalOut:
    signal = read.signal
    return CandidateSignalOut(
        key=signal.signal_key,
        label=read.label,
        rule_kind=signal.rule_kind,
        outcome=signal.outcome,
        strength=signal.strength,
        weight_applied=signal.weight_applied,
        contribution=signal.contribution,
        explanation=signal.explanation,
        raw_value=signal.raw_value,
    )


def _job_out(read: CandidateRead, *, prior: bool) -> CandidateJobOut:
    job = read.prior_job if prior else read.followup_job
    return CandidateJobOut(
        id=job.id,
        external_id=job.external_id,
        job_number=job.job_number,
        customer_id=job.customer_id,
        location_id=job.location_id,
        equipment_id=job.equipment_id,
        technician_id=job.technician_id,
        technician_name=(
            read.technician_names.get(job.technician_id) if job.technician_id else None
        ),
        status=job.status,
        service_date=job.service_date,
        scheduled_at=job.scheduled_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        raw_service_category=job.raw_service_category,
        raw_job_type=job.raw_job_type,
        summary=job.summary,
        description=job.description,
        symptoms_text=job.symptoms_text,
        diagnosis_text=job.diagnosis_text,
        resolution_text=job.resolution_text,
        invoice_number=job.invoice_number,
        revenue_amount=job.revenue_amount,
        parts_amount=job.parts_amount,
        labor_amount=job.labor_amount,
        currency_code=job.currency_code,
        is_warranty=job.is_warranty,
        is_no_charge=job.is_no_charge,
        warranty_reference=job.warranty_reference,
    )


def _candidate_summary(read: CandidateRead) -> CandidateSummaryOut:
    candidate = read.candidate
    if candidate.current_normalized_score is None or candidate.score_band is None:
        raise RuntimeError("Candidate is missing its current score.")
    return CandidateSummaryOut(
        id=candidate.id,
        score=candidate.current_normalized_score,
        band=candidate.score_band,
        days_between=candidate.days_between,
        is_suppressed=candidate.is_suppressed,
        suppression_reason=candidate.suppression_reason,
        suppressed_by_signal_key=candidate.suppressed_by_signal_key,
        workflow_status=candidate.workflow_status,
        prior_job=_job_out(read, prior=True),
        followup_job=_job_out(read, prior=False),
        customer=(CandidateCustomerOut.model_validate(read.customer) if read.customer else None),
        equipment=(
            CandidateEquipmentOut.model_validate(read.equipment) if read.equipment else None
        ),
        current_review=(
            ReworkReviewOut.model_validate(read.current_review) if read.current_review else None
        ),
        top_signals=[_signal_out(signal) for signal in read.signals[:3]],
        detected_at=candidate.first_detected_at,
    )


@router.get("/rework")
async def list_candidates_endpoint(
    org_id: UUID,
    min_score: Decimal | None = Query(default=None, ge=0, le=100),
    band: ScoreBand | None = None,
    workflow_status: CandidateWorkflowStatus = Query(
        default=CandidateWorkflowStatus.OPEN, alias="status"
    ),
    include_suppressed: bool = False,
    customer_id: UUID | None = None,
    equipment_id: UUID | None = None,
    technician_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: CandidateSort = CandidateSort.SCORE,
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_rework_read),
) -> CandidateListOut:
    del org_id
    page_limit = clamp_limit(limit)
    try:
        candidates, next_cursor = await DetectionRepository(session, tenant).list_candidates(
            min_score=min_score,
            band=band,
            workflow_status=workflow_status,
            include_suppressed=include_suppressed,
            customer_id=customer_id,
            equipment_id=equipment_id,
            technician_id=technician_id,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            cursor=cursor,
            limit=page_limit,
        )
    except InvalidCursorError as exc:
        raise InvalidCursorRequestError("Cursor is malformed or expired.") from exc
    return CandidateListOut(
        data=[_candidate_summary(candidate) for candidate in candidates],
        page=CandidatePageOut(
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            limit=page_limit,
        ),
    )


@router.get("/rework/{candidate_id}")
async def get_candidate_endpoint(
    org_id: UUID,
    candidate_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_rework_read),
) -> CandidateDetailOut:
    del org_id
    candidate = await DetectionRepository(session, tenant).get_candidate(candidate_id)
    if candidate is None:
        raise NotFoundError("Candidate not found.")
    summary = _candidate_summary(candidate)
    return CandidateDetailOut(
        **summary.model_dump(),
        signals=[_signal_out(signal) for signal in candidate.signals],
    )


@router.get("/settings/categories")
async def list_review_categories_endpoint(
    org_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_rework_read),
) -> list[ReworkCategoryOut]:
    del org_id
    categories = await list_review_categories(session, organization_id=tenant.organization_id)
    return [ReworkCategoryOut.model_validate(category) for category in categories]


@router.get("/settings/root-causes")
async def list_root_causes_endpoint(
    org_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_rework_read),
) -> list[RootCauseOut]:
    del org_id
    root_causes = await list_root_causes(session, organization_id=tenant.organization_id)
    return [RootCauseOut.model_validate(root_cause) for root_cause in root_causes]


@router.get("/rework/{candidate_id}/reviews")
async def list_review_history_endpoint(
    org_id: UUID,
    candidate_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_rework_read),
) -> list[ReworkReviewOut]:
    del org_id
    reviews = await list_review_history(
        session,
        organization_id=tenant.organization_id,
        candidate_id=candidate_id,
    )
    return [ReworkReviewOut.model_validate(review) for review in reviews]


@router.post("/rework/{candidate_id}/review", status_code=status.HTTP_201_CREATED)
async def create_review_endpoint(
    org_id: UUID,
    candidate_id: UUID,
    body: CreateReviewRequest,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_rework_review),
    user: AuthenticatedUser = Depends(require_session),
) -> ReworkReviewOut:
    del org_id
    async with tenant_session(app_state.session_factory, tenant) as session:
        review = await record_review(
            session,
            organization_id=tenant.organization_id,
            candidate_id=candidate_id,
            decision=body.decision,
            category_id=body.category_id,
            root_cause_id=body.root_cause_id,
            note=body.note,
            reviewed_by_user_id=user.id,
            reviewer_label=user.full_name,
            request_id=tenant.request_id,
        )
        return ReworkReviewOut.model_validate(review)
