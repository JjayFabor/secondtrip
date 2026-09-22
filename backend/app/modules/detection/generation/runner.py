"""Stream blocked pairs and upsert stable candidate identities in bounded chunks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.detection.models import ReworkCandidate
from app.modules.detection.schemas import CandidateSuppressionReason
from app.modules.jobs.read_models import CANDIDATE_PAIR_QUERY, detection_job_ids_in_scope


@dataclass(frozen=True, slots=True)
class CandidatePairRecord:
    prior_job_id: UUID
    followup_job_id: UUID
    customer_id: UUID | None
    location_id: UUID | None
    equipment_id: UUID | None
    technician_prior_id: UUID | None
    technician_followup_id: UUID | None
    days_between: int


@dataclass(frozen=True, slots=True)
class CandidateGenerationOutcome:
    pairs_evaluated: int
    candidates_created: int
    candidates_updated: int
    candidates_suppressed: int


async def generate_candidates(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rule_set_id: UUID,
    detection_run_id: UUID,
    from_date: date,
    to_date: date,
    window_days: int,
    max_followups_per_job: int,
    chunk_size: int = 500,
) -> CandidateGenerationOutcome:
    """Generate and stable-upsert every qualifying pair for one tenant scope."""

    _validate_scope(
        from_date=from_date,
        to_date=to_date,
        window_days=window_days,
        max_followups_per_job=max_followups_per_job,
        chunk_size=chunk_size,
    )
    created = 0
    updated = 0
    chunk: list[CandidatePairRecord] = []
    async for pair in _stream_pairs(
        session,
        organization_id=organization_id,
        from_date=from_date,
        to_date=to_date,
        window_days=window_days,
        max_followups_per_job=max_followups_per_job,
    ):
        chunk.append(pair)
        if len(chunk) == chunk_size:
            chunk_created, chunk_updated = await _upsert_chunk(
                session,
                organization_id=organization_id,
                rule_set_id=rule_set_id,
                detection_run_id=detection_run_id,
                pairs=chunk,
            )
            created += chunk_created
            updated += chunk_updated
            chunk = []
    if chunk:
        chunk_created, chunk_updated = await _upsert_chunk(
            session,
            organization_id=organization_id,
            rule_set_id=rule_set_id,
            detection_run_id=detection_run_id,
            pairs=chunk,
        )
        created += chunk_created
        updated += chunk_updated
    candidates_suppressed = await _suppress_no_longer_qualifying(
        session,
        organization_id=organization_id,
        rule_set_id=rule_set_id,
        detection_run_id=detection_run_id,
        from_date=from_date,
        to_date=to_date,
        window_days=window_days,
    )
    return CandidateGenerationOutcome(
        pairs_evaluated=created + updated,
        candidates_created=created,
        candidates_updated=updated,
        candidates_suppressed=candidates_suppressed,
    )


async def _stream_pairs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    from_date: date,
    to_date: date,
    window_days: int,
    max_followups_per_job: int,
) -> AsyncIterator[CandidatePairRecord]:
    result = await session.stream(
        CANDIDATE_PAIR_QUERY,
        {
            "organization_id": organization_id,
            "from_date": from_date,
            "to_date": to_date,
            "window_days": window_days,
            "max_followups_per_job": max_followups_per_job,
        },
    )
    async for row in result.mappings():
        yield CandidatePairRecord(
            prior_job_id=cast(UUID, row["prior_job_id"]),
            followup_job_id=cast(UUID, row["followup_job_id"]),
            customer_id=cast(UUID | None, row["customer_id"]),
            location_id=cast(UUID | None, row["location_id"]),
            equipment_id=cast(UUID | None, row["equipment_id"]),
            technician_prior_id=cast(UUID | None, row["technician_prior_id"]),
            technician_followup_id=cast(UUID | None, row["technician_followup_id"]),
            days_between=cast(int, row["days_between"]),
        )


async def _upsert_chunk(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rule_set_id: UUID,
    detection_run_id: UUID,
    pairs: list[CandidatePairRecord],
) -> tuple[int, int]:
    pair_keys = [(pair.prior_job_id, pair.followup_job_id) for pair in pairs]
    existing = set(
        (
            await session.execute(
                select(ReworkCandidate.prior_job_id, ReworkCandidate.followup_job_id).where(
                    ReworkCandidate.organization_id == organization_id,
                    tuple_(
                        ReworkCandidate.prior_job_id,
                        ReworkCandidate.followup_job_id,
                    ).in_(pair_keys),
                )
            )
        ).all()
    )
    now = datetime.now(UTC)
    values = [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "prior_job_id": pair.prior_job_id,
            "followup_job_id": pair.followup_job_id,
            "customer_id": pair.customer_id,
            "location_id": pair.location_id,
            "equipment_id": pair.equipment_id,
            "technician_prior_id": pair.technician_prior_id,
            "technician_followup_id": pair.technician_followup_id,
            "days_between": pair.days_between,
            "current_rule_set_id": rule_set_id,
            "current_detection_run_id": detection_run_id,
            "is_suppressed": False,
            "suppression_reason": None,
            "suppressed_by_signal_key": None,
            "first_detected_at": now,
            "last_evaluated_at": now,
            "created_at": now,
            "updated_at": now,
        }
        for pair in pairs
    ]
    statement = insert(ReworkCandidate).values(values)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            constraint="rework_candidates_org_pair_key",
            set_={
                "customer_id": excluded.customer_id,
                "location_id": excluded.location_id,
                "equipment_id": excluded.equipment_id,
                "technician_prior_id": excluded.technician_prior_id,
                "technician_followup_id": excluded.technician_followup_id,
                "days_between": excluded.days_between,
                "current_rule_set_id": excluded.current_rule_set_id,
                "current_detection_run_id": excluded.current_detection_run_id,
                "is_suppressed": False,
                "suppression_reason": None,
                "suppressed_by_signal_key": None,
                "last_evaluated_at": now,
                "updated_at": now,
            },
        )
    )
    updated = len(existing)
    return len(pairs) - updated, updated


async def _suppress_no_longer_qualifying(
    session: AsyncSession,
    *,
    organization_id: UUID,
    rule_set_id: UUID,
    detection_run_id: UUID,
    from_date: date,
    to_date: date,
    window_days: int,
) -> int:
    scoped_job_ids = detection_job_ids_in_scope(
        organization_id=organization_id,
        from_date=from_date,
        to_date=to_date,
        window_days=window_days,
    )
    result = await session.execute(
        update(ReworkCandidate)
        .where(
            ReworkCandidate.organization_id == organization_id,
            ReworkCandidate.current_detection_run_id.is_distinct_from(detection_run_id),
            ReworkCandidate.prior_job_id.in_(scoped_job_ids),
            ReworkCandidate.followup_job_id.in_(scoped_job_ids),
        )
        .values(
            current_rule_set_id=rule_set_id,
            current_detection_run_id=detection_run_id,
            is_suppressed=True,
            suppression_reason=CandidateSuppressionReason.OUT_OF_WINDOW,
            suppressed_by_signal_key=None,
            last_evaluated_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    return result.rowcount  # type: ignore[attr-defined, no-any-return]


def _validate_scope(
    *,
    from_date: date,
    to_date: date,
    window_days: int,
    max_followups_per_job: int,
    chunk_size: int,
) -> None:
    if from_date > to_date:
        raise ValueError("from_date must be on or before to_date")
    if window_days < 1:
        raise ValueError("window_days must be positive")
    if max_followups_per_job < 1:
        raise ValueError("max_followups_per_job must be positive")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
