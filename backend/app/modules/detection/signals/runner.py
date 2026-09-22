"""Bulk-load signal context, score candidates, and persist explainable evidence."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.customers.service import get_equipment_detection_data
from app.modules.detection.models import (
    CandidateScoreHistory,
    CandidateSignal,
    DetectionRule,
    DetectionRuleSet,
    ReworkCandidate,
)
from app.modules.detection.schemas import CandidateSuppressionReason, ScoreBand
from app.modules.detection.scoring.calculator import ScoringRule, ScoringRuleSet, score
from app.modules.detection.signals.base import CandidatePair, JobSignalData, SignalResult
from app.modules.detection.signals.registry import evaluate_signals
from app.modules.jobs.read_models import (
    DetectionJob,
    load_detection_jobs,
    load_detection_part_codes,
    load_detection_visits,
)

CENT = Decimal("0.01")
EVIDENCE_UPSERT_SIZE = 1_000


@dataclass(frozen=True, slots=True)
class CandidateEvaluationOutcome:
    candidates_evaluated: int
    candidates_suppressed: int


async def evaluate_and_score_candidates(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rule_set_id: UUID,
    detection_run_id: UUID,
    chunk_size: int = 500,
) -> CandidateEvaluationOutcome:
    """Evaluate the current run in bounded chunks and persist its evidence."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    rule_set = await session.scalar(
        select(DetectionRuleSet).where(
            DetectionRuleSet.organization_id == organization_id,
            DetectionRuleSet.id == rule_set_id,
        )
    )
    if rule_set is None:
        raise ValueError("rule set was not found in the organization")
    rules = list(
        (
            await session.execute(
                select(DetectionRule)
                .where(
                    DetectionRule.organization_id == organization_id,
                    DetectionRule.rule_set_id == rule_set_id,
                    DetectionRule.is_enabled.is_(True),
                )
                .order_by(DetectionRule.sort_order, DetectionRule.signal_key)
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        raise ValueError("rule set has no enabled rules")

    configured_params = {rule.signal_key: dict(rule.params) for rule in rules}
    scoring_rules = ScoringRuleSet(
        rules={
            rule.signal_key: ScoringRule(
                key=rule.signal_key,
                kind=rule.kind,
                weight=rule.weight,
            )
            for rule in rules
        }
    )

    evaluated = 0
    suppressed = 0
    cursor: UUID | None = None
    while True:
        rows = await _candidate_rows(
            session,
            organization_id=organization_id,
            detection_run_id=detection_run_id,
            after_id=cursor,
            chunk_size=chunk_size,
        )
        if not rows:
            break
        pairs = await _build_pairs(
            session,
            organization_id=organization_id,
            rows=rows,
            window_days=rule_set.window_days,
        )
        evidence_values: list[dict[str, object]] = []
        history_values: list[dict[str, object]] = []
        for candidate, pair in zip(rows, pairs, strict=True):
            results = evaluate_signals(pair, configured_params)
            outcome = score(results, scoring_rules)
            candidate.current_score = _money(outcome.raw)
            candidate.current_normalized_score = _money(outcome.normalized)
            candidate.score_band = outcome.band
            candidate.is_suppressed = outcome.suppressed
            candidate.suppression_reason = (
                CandidateSuppressionReason.SIGNAL_VETO if outcome.suppressed else None
            )
            candidate.suppressed_by_signal_key = outcome.suppressed_by
            evidence_values.extend(
                _evidence_values(
                    organization_id=organization_id,
                    detection_run_id=detection_run_id,
                    candidate_id=candidate.id,
                    rules=rules,
                    results=results,
                    contributions=outcome.contributions,
                )
            )
            history_values.append(
                _history_value(
                    organization_id=organization_id,
                    rule_set_id=rule_set_id,
                    detection_run_id=detection_run_id,
                    candidate_id=candidate.id,
                    raw_score=candidate.current_score,
                    normalized_score=candidate.current_normalized_score,
                    score_band=outcome.band,
                    is_suppressed=outcome.suppressed,
                )
            )
            evaluated += 1
            suppressed += int(outcome.suppressed)
        await _persist_evidence(session, evidence_values)
        await _persist_history(session, history_values)
        await session.flush()
        cursor = rows[-1].id

    return CandidateEvaluationOutcome(
        candidates_evaluated=evaluated,
        candidates_suppressed=suppressed,
    )


async def _candidate_rows(
    session: AsyncSession,
    *,
    organization_id: UUID,
    detection_run_id: UUID,
    after_id: UUID | None,
    chunk_size: int,
) -> Sequence[ReworkCandidate]:
    statement = (
        select(ReworkCandidate)
        .where(
            ReworkCandidate.organization_id == organization_id,
            ReworkCandidate.current_detection_run_id == detection_run_id,
            ReworkCandidate.suppression_reason.is_distinct_from(
                CandidateSuppressionReason.OUT_OF_WINDOW
            ),
        )
        .order_by(ReworkCandidate.id)
        .limit(chunk_size)
    )
    if after_id is not None:
        statement = statement.where(ReworkCandidate.id > after_id)
    return (await session.execute(statement)).scalars().all()


async def _build_pairs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rows: Sequence[ReworkCandidate],
    window_days: int,
) -> list[CandidatePair]:
    job_ids = {job_id for candidate in rows for job_id in candidate_pair_ids(candidate)}
    jobs_by_id = await load_detection_jobs(
        session,
        organization_id=organization_id,
        job_ids=job_ids,
    )
    part_codes = await load_detection_part_codes(
        session,
        organization_id=organization_id,
        job_ids=job_ids,
    )

    equipment_ids = {
        equipment_id
        for candidate in rows
        if (equipment_id := jobs_by_id[candidate.followup_job_id].equipment_id) is not None
    }
    equipment_by_id = await get_equipment_detection_data(
        session,
        organization_id=organization_id,
        equipment_ids=equipment_ids,
    )

    customer_ids = {
        customer_id
        for candidate in rows
        if (customer_id := jobs_by_id[candidate.prior_job_id].customer_id) is not None
    }
    prior_equipment_ids = {
        equipment_id
        for candidate in rows
        if (equipment_id := jobs_by_id[candidate.prior_job_id].equipment_id) is not None
    }
    visits_by_customer: defaultdict[UUID, list[tuple[UUID, date]]] = defaultdict(list)
    visits_by_equipment: defaultdict[UUID, list[tuple[UUID, date]]] = defaultdict(list)
    if customer_ids or prior_equipment_ids:
        first_date = min(jobs_by_id[row.prior_job_id].service_date for row in rows)
        last_date = max(
            jobs_by_id[row.prior_job_id].service_date + timedelta(days=window_days) for row in rows
        )
        visit_rows = await load_detection_visits(
            session,
            organization_id=organization_id,
            customer_ids=customer_ids,
            equipment_ids=prior_equipment_ids,
            first_date=first_date,
            last_date=last_date,
        )
        for visit in visit_rows:
            job_id = visit.id
            customer_id = visit.customer_id
            equipment_id = visit.equipment_id
            service_date = visit.service_date
            if customer_id is not None:
                visits_by_customer[customer_id].append((job_id, service_date))
            if equipment_id is not None:
                visits_by_equipment[equipment_id].append((job_id, service_date))

    pairs: list[CandidatePair] = []
    for candidate in rows:
        prior = jobs_by_id[candidate.prior_job_id]
        followup = jobs_by_id[candidate.followup_job_id]
        equipment = (
            equipment_by_id.get(followup.equipment_id)
            if followup.equipment_id is not None
            else None
        )
        equipment_serial = equipment.serial_number if equipment else None
        warranty_expires_on = equipment.warranty_expires_on if equipment else None
        related_visits: dict[UUID, date] = {}
        if prior.customer_id is not None:
            related_visits.update(visits_by_customer[prior.customer_id])
        if prior.equipment_id is not None:
            related_visits.update(visits_by_equipment[prior.equipment_id])
        end_date = prior.service_date + timedelta(days=window_days)
        recurrence_count = sum(
            prior.service_date <= service_date <= end_date
            for service_date in related_visits.values()
        )
        pairs.append(
            CandidatePair(
                candidate_id=candidate.id,
                prior=_job_data(prior, part_codes[prior.id]),
                followup=_job_data(followup, part_codes[followup.id]),
                days_between=candidate.days_between,
                recurrence_count=recurrence_count,
                equipment_serial=equipment_serial,
                equipment_warranty_expires_on=warranty_expires_on,
            )
        )
    return pairs


def candidate_pair_ids(candidate: ReworkCandidate) -> tuple[UUID, UUID]:
    return candidate.prior_job_id, candidate.followup_job_id


def _job_data(job: DetectionJob, part_codes: set[str]) -> JobSignalData:
    return JobSignalData(
        id=job.id,
        customer_id=job.customer_id,
        location_id=job.location_id,
        equipment_id=job.equipment_id,
        technician_id=job.technician_id,
        service_category_id=job.service_category_id,
        service_category=job.raw_service_category,
        raw_job_type=job.raw_job_type,
        service_date=job.service_date,
        revenue_amount=job.revenue_amount,
        is_warranty=job.is_warranty,
        extra_fields=job.extra_fields,
        part_codes=frozenset(part_codes),
    )


def _evidence_values(
    *,
    organization_id: UUID,
    detection_run_id: UUID,
    candidate_id: UUID,
    rules: Sequence[DetectionRule],
    results: Sequence[SignalResult],
    contributions: Mapping[str, Decimal],
) -> list[dict[str, object]]:
    rules_by_key = {rule.signal_key: rule for rule in rules}
    return [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "candidate_id": candidate_id,
            "detection_run_id": detection_run_id,
            "signal_key": result.key,
            "rule_kind": rules_by_key[result.key].kind,
            "outcome": result.outcome,
            "strength": result.strength,
            "raw_value": result.raw_value,
            "weight_applied": rules_by_key[result.key].weight,
            "contribution": _money(contributions[result.key]),
            "explanation": result.explanation,
        }
        for result in results
    ]


async def _persist_evidence(
    session: AsyncSession,
    values: list[dict[str, object]],
) -> None:
    for offset in range(0, len(values), EVIDENCE_UPSERT_SIZE):
        statement = insert(CandidateSignal).values(values[offset : offset + EVIDENCE_UPSERT_SIZE])
        excluded = statement.excluded
        await session.execute(
            statement.on_conflict_do_update(
                constraint="candidate_signals_candidate_run_signal_key",
                set_={
                    "rule_kind": excluded.rule_kind,
                    "outcome": excluded.outcome,
                    "strength": excluded.strength,
                    "raw_value": excluded.raw_value,
                    "weight_applied": excluded.weight_applied,
                    "contribution": excluded.contribution,
                    "explanation": excluded.explanation,
                },
            )
        )


def _history_value(
    *,
    organization_id: UUID,
    rule_set_id: UUID,
    detection_run_id: UUID,
    candidate_id: UUID,
    raw_score: Decimal,
    normalized_score: Decimal,
    score_band: ScoreBand,
    is_suppressed: bool,
) -> dict[str, object]:
    return {
        "id": new_id(),
        "organization_id": organization_id,
        "candidate_id": candidate_id,
        "detection_run_id": detection_run_id,
        "rule_set_id": rule_set_id,
        "raw_score": raw_score,
        "normalized_score": normalized_score,
        "score_band": score_band,
        "is_suppressed": is_suppressed,
    }


async def _persist_history(
    session: AsyncSession,
    values: list[dict[str, object]],
) -> None:
    statement = insert(CandidateScoreHistory).values(values)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            constraint="candidate_score_history_candidate_run_key",
            set_={
                "rule_set_id": excluded.rule_set_id,
                "raw_score": excluded.raw_score,
                "normalized_score": excluded.normalized_score,
                "score_band": excluded.score_band,
                "is_suppressed": excluded.is_suppressed,
            },
        )
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
