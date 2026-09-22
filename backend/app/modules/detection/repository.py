"""Tenant-scoped candidate queue and evidence reads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.pagination import InvalidCursorError, decode_cursor, encode_cursor
from app.core.tenancy import TenantContext
from app.modules.customers.read_models import (
    CandidateCustomer,
    CandidateEquipment,
    load_candidate_customers,
    load_candidate_equipment,
)
from app.modules.detection.models import (
    CandidateSignal,
    DetectionSignalDefinition,
    ReworkCandidate,
    ReworkReview,
)
from app.modules.detection.schemas import (
    CandidateSort,
    CandidateWorkflowStatus,
    ScoreBand,
)
from app.modules.jobs.read_models import (
    CandidateJob,
    candidate_job_ids_in_date_range,
    load_candidate_jobs,
)
from app.modules.workforce.read_models import load_candidate_technician_names


@dataclass(frozen=True, slots=True)
class SignalRead:
    signal: CandidateSignal
    label: str


@dataclass(frozen=True, slots=True)
class CandidateRead:
    candidate: ReworkCandidate
    prior_job: CandidateJob
    followup_job: CandidateJob
    customer: CandidateCustomer | None
    equipment: CandidateEquipment | None
    technician_names: dict[UUID, str]
    current_review: ReworkReview | None
    signals: list[SignalRead]


class DetectionRepository:
    def __init__(self, session: AsyncSession, tenant: TenantContext) -> None:
        self._session = session
        self._tenant = tenant

    async def list_candidates(
        self,
        *,
        min_score: Decimal | None,
        band: ScoreBand | None,
        workflow_status: CandidateWorkflowStatus,
        include_suppressed: bool,
        customer_id: UUID | None,
        equipment_id: UUID | None,
        technician_id: UUID | None,
        date_from: date | None,
        date_to: date | None,
        sort: CandidateSort,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[CandidateRead], str | None]:
        statement = select(ReworkCandidate).where(
            ReworkCandidate.organization_id == self._tenant.organization_id,
            ReworkCandidate.current_normalized_score.is_not(None),
            ReworkCandidate.score_band.is_not(None),
            ReworkCandidate.workflow_status == workflow_status,
        )
        if not include_suppressed:
            statement = statement.where(ReworkCandidate.is_suppressed.is_(False))
        if min_score is not None:
            statement = statement.where(ReworkCandidate.current_normalized_score >= min_score)
        if band is not None:
            statement = statement.where(ReworkCandidate.score_band == band)
        if customer_id is not None:
            statement = statement.where(ReworkCandidate.customer_id == customer_id)
        if equipment_id is not None:
            statement = statement.where(ReworkCandidate.equipment_id == equipment_id)
        if technician_id is not None:
            statement = statement.where(
                or_(
                    ReworkCandidate.technician_prior_id == technician_id,
                    ReworkCandidate.technician_followup_id == technician_id,
                )
            )
        if date_from is not None or date_to is not None:
            followups = candidate_job_ids_in_date_range(
                organization_id=self._tenant.organization_id,
                date_from=date_from,
                date_to=date_to,
            )
            statement = statement.where(ReworkCandidate.followup_job_id.in_(followups))

        sort_column = self._sort_column(sort)
        if cursor is not None:
            raw_sort_value, cursor_id = decode_cursor(cursor)
            try:
                cursor_value = self._parse_cursor_value(sort, raw_sort_value)
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise InvalidCursorError("Cursor is malformed or expired.") from exc
            statement = statement.where(
                or_(
                    sort_column < cursor_value,
                    and_(sort_column == cursor_value, ReworkCandidate.id < cursor_id),
                )
            )
        statement = statement.order_by(desc(sort_column), desc(ReworkCandidate.id)).limit(limit + 1)
        candidates = list((await self._session.execute(statement)).scalars().all())
        has_more = len(candidates) > limit
        if has_more:
            candidates = candidates[:limit]

        next_cursor = None
        if has_more and candidates:
            last = candidates[-1]
            sort_value = self._candidate_sort_value(last, sort)
            next_cursor = encode_cursor(sort_value=sort_value, id=last.id)
        return await self._hydrate(candidates), next_cursor

    async def get_candidate(self, candidate_id: UUID) -> CandidateRead | None:
        candidate = await self._session.scalar(
            select(ReworkCandidate).where(
                ReworkCandidate.organization_id == self._tenant.organization_id,
                ReworkCandidate.id == candidate_id,
            )
        )
        if candidate is None:
            return None
        hydrated = await self._hydrate([candidate])
        return hydrated[0]

    async def _hydrate(self, candidates: list[ReworkCandidate]) -> list[CandidateRead]:
        if not candidates:
            return []
        organization_id = self._tenant.organization_id
        candidate_ids = {candidate.id for candidate in candidates}
        job_ids = {
            job_id
            for candidate in candidates
            for job_id in (candidate.prior_job_id, candidate.followup_job_id)
        }
        jobs = await load_candidate_jobs(
            self._session,
            organization_id=organization_id,
            job_ids=job_ids,
        )
        customer_ids = {candidate.customer_id for candidate in candidates if candidate.customer_id}
        customers = await load_candidate_customers(
            self._session,
            organization_id=organization_id,
            customer_ids=customer_ids,
        )
        equipment_ids = {
            candidate.equipment_id for candidate in candidates if candidate.equipment_id
        }
        equipment = await load_candidate_equipment(
            self._session,
            organization_id=organization_id,
            equipment_ids=equipment_ids,
        )
        technician_ids = {job.technician_id for job in jobs.values() if job.technician_id}
        technician_names = await load_candidate_technician_names(
            self._session,
            organization_id=organization_id,
            technician_ids=technician_ids,
        )
        current_reviews = {
            review.candidate_id: review
            for review in (
                (
                    await self._session.execute(
                        select(ReworkReview).where(
                            ReworkReview.organization_id == organization_id,
                            ReworkReview.candidate_id.in_(candidate_ids),
                            ReworkReview.superseded_by_review_id.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
        }
        signal_rows = (
            await self._session.execute(
                select(CandidateSignal, DetectionSignalDefinition.label)
                .join(
                    DetectionSignalDefinition,
                    DetectionSignalDefinition.key == CandidateSignal.signal_key,
                )
                .join(
                    ReworkCandidate,
                    and_(
                        ReworkCandidate.organization_id == CandidateSignal.organization_id,
                        ReworkCandidate.id == CandidateSignal.candidate_id,
                        ReworkCandidate.current_detection_run_id
                        == CandidateSignal.detection_run_id,
                    ),
                )
                .where(
                    CandidateSignal.organization_id == organization_id,
                    CandidateSignal.candidate_id.in_(candidate_ids),
                )
                .order_by(
                    CandidateSignal.candidate_id,
                    CandidateSignal.contribution.desc(),
                    CandidateSignal.signal_key,
                )
            )
        ).all()
        signals: dict[UUID, list[SignalRead]] = {candidate_id: [] for candidate_id in candidate_ids}
        for signal, label in signal_rows:
            signals[signal.candidate_id].append(SignalRead(signal=signal, label=label))

        result: list[CandidateRead] = []
        for candidate in candidates:
            prior_job = jobs.get(candidate.prior_job_id)
            followup_job = jobs.get(candidate.followup_job_id)
            if prior_job is None or followup_job is None:
                continue
            result.append(
                CandidateRead(
                    candidate=candidate,
                    prior_job=prior_job,
                    followup_job=followup_job,
                    customer=(
                        customers.get(candidate.customer_id) if candidate.customer_id else None
                    ),
                    equipment=(
                        equipment.get(candidate.equipment_id) if candidate.equipment_id else None
                    ),
                    technician_names=technician_names,
                    current_review=current_reviews.get(candidate.id),
                    signals=signals[candidate.id],
                )
            )
        return result

    @staticmethod
    def _sort_column(sort: CandidateSort) -> InstrumentedAttribute[Any]:
        if sort is CandidateSort.DAYS_BETWEEN:
            return ReworkCandidate.days_between
        if sort is CandidateSort.DETECTED_AT:
            return ReworkCandidate.first_detected_at
        return ReworkCandidate.current_normalized_score

    @staticmethod
    def _parse_cursor_value(sort: CandidateSort, value: object) -> Decimal | int | datetime:
        if sort is CandidateSort.SCORE:
            return Decimal(str(value))
        if sort is CandidateSort.DAYS_BETWEEN:
            return int(str(value))
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    @staticmethod
    def _candidate_sort_value(
        candidate: ReworkCandidate, sort: CandidateSort
    ) -> str | int | datetime:
        if sort is CandidateSort.DAYS_BETWEEN:
            return candidate.days_between
        if sort is CandidateSort.DETECTED_AT:
            return candidate.first_detected_at
        if candidate.current_normalized_score is None:
            raise ValueError("Scored candidate is missing its normalized score.")
        return str(candidate.current_normalized_score)
