from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.settings import Settings
from app.modules.customers.models import Customer, Equipment
from app.modules.detection.defaults import DEFAULT_SIGNAL_KEYS
from app.modules.detection.generation.runner import generate_candidates
from app.modules.detection.models import (
    CandidateScoreHistory,
    CandidateSignal,
    DetectionRun,
    ReworkCandidate,
)
from app.modules.detection.schemas import (
    CandidateSuppressionReason,
    DetectionRunStatus,
    DetectionTrigger,
)
from app.modules.detection.service import ensure_default_rule_set
from app.modules.detection.signals.runner import evaluate_and_score_candidates
from app.modules.identity.models import User, UserStatus
from app.modules.imports import models as import_models  # noqa: F401 - registers FK metadata
from app.modules.jobs.models import Job, SourceSystem, SourceSystemKind
from app.modules.jobs.schemas import JobStatus
from app.modules.organizations.models import Organization, OrganizationMembership
from app.modules.tasks import models as task_models  # noqa: F401 - registers FK metadata
from app.modules.workforce import models as workforce_models  # noqa: F401 - registers FK metadata


async def test_blocked_generation_and_rerun_preserve_candidate_identity(
    owner_engine: AsyncEngine,
    settings: Settings,
) -> None:
    connection = await owner_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, expire_on_commit=False)
    try:
        user = User(
            email=f"candidate-generation-{uuid4()}@example.test",
            full_name="Candidate Generation",
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()

        org_a = await _add_organization(session, user.id, "candidate-a")
        org_b = await _add_organization(session, user.id, "candidate-b")
        source_a = await _add_source(session, org_a.id, "source-a")
        source_b = await _add_source(session, org_b.id, "source-b")

        same_day_customer = await _add_customer(session, org_a.id, "same-day")
        same_day_prior = await _add_job(
            session,
            org_a.id,
            source_a.id,
            same_day_customer.id,
            "same-day-prior",
            date(2026, 3, 1),
            started_at=None,
        )
        same_day_followup = await _add_job(
            session,
            org_a.id,
            source_a.id,
            same_day_customer.id,
            "same-day-followup",
            date(2026, 3, 1),
            started_at=datetime(2026, 3, 1, 9, tzinfo=UTC),
        )

        boundary_customer = await _add_customer(session, org_a.id, "boundary")
        boundary_prior = await _add_job(
            session,
            org_a.id,
            source_a.id,
            boundary_customer.id,
            "boundary-prior",
            date(2026, 1, 1),
        )
        boundary_in = await _add_job(
            session,
            org_a.id,
            source_a.id,
            boundary_customer.id,
            "boundary-in",
            date(2026, 1, 31),
            status=JobStatus.UNKNOWN,
        )
        boundary_out = await _add_job(
            session,
            org_a.id,
            source_a.id,
            boundary_customer.id,
            "boundary-out",
            date(2026, 2, 1),
        )

        cancelled_customer = await _add_customer(session, org_a.id, "cancelled")
        cancelled_prior = await _add_job(
            session,
            org_a.id,
            source_a.id,
            cancelled_customer.id,
            "cancelled-prior",
            date(2026, 3, 10),
        )
        cancelled = await _add_job(
            session,
            org_a.id,
            source_a.id,
            cancelled_customer.id,
            "cancelled",
            date(2026, 3, 12),
            status=JobStatus.CANCELLED,
        )
        cancelled_followup = await _add_job(
            session,
            org_a.id,
            source_a.id,
            cancelled_customer.id,
            "cancelled-followup",
            date(2026, 3, 15),
        )

        equipment = Equipment(
            organization_id=org_a.id,
            natural_key_hash=b"shared-equipment",
            serial_number="SHARED-001",
        )
        session.add(equipment)
        await session.flush()
        equipment_customer_a = await _add_customer(session, org_a.id, "equipment-a")
        equipment_customer_b = await _add_customer(session, org_a.id, "equipment-b")
        equipment_prior = await _add_job(
            session,
            org_a.id,
            source_a.id,
            equipment_customer_a.id,
            "equipment-prior",
            date(2026, 4, 1),
            equipment_id=equipment.id,
        )
        equipment_followup = await _add_job(
            session,
            org_a.id,
            source_a.id,
            equipment_customer_b.id,
            "equipment-followup",
            date(2026, 4, 5),
            equipment_id=equipment.id,
        )

        fanout_customer = await _add_customer(session, org_a.id, "fanout")
        fanout_jobs = [
            await _add_job(
                session,
                org_a.id,
                source_a.id,
                fanout_customer.id,
                f"fanout-{offset}",
                date(2026, 5, 1) + timedelta(days=offset),
            )
            for offset in range(6)
        ]

        other_customer = await _add_customer(session, org_b.id, "same-day")
        other_job = await _add_job(
            session,
            org_b.id,
            source_b.id,
            other_customer.id,
            "other-tenant",
            date(2026, 3, 2),
        )

        rule_set = await ensure_default_rule_set(
            session,
            settings,
            organization_id=org_a.id,
            created_by_user_id=user.id,
        )
        first_run = DetectionRun(
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            trigger=DetectionTrigger.MANUAL,
            status=DetectionRunStatus.RUNNING,
        )
        session.add(first_run)
        await session.flush()

        first = await generate_candidates(
            session,
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            detection_run_id=first_run.id,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 6, 1),
            window_days=30,
            max_followups_per_job=2,
            chunk_size=2,
        )
        candidates = list(
            (
                await session.execute(
                    select(ReworkCandidate).where(ReworkCandidate.organization_id == org_a.id)
                )
            )
            .scalars()
            .all()
        )
        pairs = {(row.prior_job_id, row.followup_job_id) for row in candidates}

        assert first.pairs_evaluated == len(candidates)
        assert first.candidates_created == len(candidates)
        assert first.candidates_updated == 0
        assert (same_day_prior.id, same_day_followup.id) in pairs
        assert (boundary_prior.id, boundary_in.id) in pairs
        assert (boundary_prior.id, boundary_out.id) not in pairs
        assert (cancelled_prior.id, cancelled_followup.id) in pairs
        assert all(cancelled.id not in pair for pair in pairs)
        assert (equipment_prior.id, equipment_followup.id) in pairs
        assert all(other_job.id not in pair for pair in pairs)

        fanout_ids = {job.id for job in fanout_jobs}
        fanout_counts = Counter(
            prior for prior, followup in pairs if prior in fanout_ids and followup in fanout_ids
        )
        assert fanout_counts[fanout_jobs[0].id] == 2
        assert all(count <= 2 for count in fanout_counts.values())

        original_ids = {
            (candidate.prior_job_id, candidate.followup_job_id): candidate.id
            for candidate in candidates
        }
        second_run = DetectionRun(
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            trigger=DetectionTrigger.MANUAL,
            status=DetectionRunStatus.RUNNING,
        )
        session.add(second_run)
        await session.flush()
        second = await generate_candidates(
            session,
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            detection_run_id=second_run.id,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 6, 1),
            window_days=30,
            max_followups_per_job=2,
            chunk_size=3,
        )
        for candidate in candidates:
            session.expire(candidate)
        rerun_candidates = list(
            (
                await session.execute(
                    select(ReworkCandidate).where(ReworkCandidate.organization_id == org_a.id)
                )
            )
            .scalars()
            .all()
        )

        assert second.candidates_created == 0
        assert second.candidates_updated == len(candidates)
        assert {
            (candidate.prior_job_id, candidate.followup_job_id): candidate.id
            for candidate in rerun_candidates
        } == original_ids
        assert all(
            candidate.current_detection_run_id == second_run.id for candidate in rerun_candidates
        )

        evaluation = await evaluate_and_score_candidates(
            session,
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            detection_run_id=second_run.id,
            chunk_size=2,
        )
        repeated_evaluation = await evaluate_and_score_candidates(
            session,
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            detection_run_id=second_run.id,
            chunk_size=3,
        )
        evidence_count = await session.scalar(
            select(func.count())
            .select_from(CandidateSignal)
            .where(CandidateSignal.detection_run_id == second_run.id)
        )
        history_count = await session.scalar(
            select(func.count())
            .select_from(CandidateScoreHistory)
            .where(CandidateScoreHistory.detection_run_id == second_run.id)
        )
        persisted_scores = (
            await session.execute(
                select(
                    ReworkCandidate.current_score,
                    ReworkCandidate.current_normalized_score,
                ).where(ReworkCandidate.current_detection_run_id == second_run.id)
            )
        ).all()

        assert evaluation.candidates_evaluated == len(rerun_candidates)
        assert repeated_evaluation == evaluation
        assert evaluation.candidates_suppressed == 0
        assert evidence_count == len(rerun_candidates) * len(DEFAULT_SIGNAL_KEYS)
        assert history_count == len(rerun_candidates)
        assert all(
            raw is not None and normalized is not None for raw, normalized in persisted_scores
        )

        narrower_run = DetectionRun(
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            trigger=DetectionTrigger.RULES_CHANGED,
            status=DetectionRunStatus.RUNNING,
        )
        session.add(narrower_run)
        await session.flush()
        narrower = await generate_candidates(
            session,
            organization_id=org_a.id,
            rule_set_id=rule_set.id,
            detection_run_id=narrower_run.id,
            from_date=date(2026, 1, 1),
            to_date=date(2026, 6, 1),
            window_days=1,
            max_followups_per_job=2,
        )
        stale_boundary = await session.scalar(
            select(ReworkCandidate).where(
                ReworkCandidate.organization_id == org_a.id,
                ReworkCandidate.prior_job_id == boundary_prior.id,
                ReworkCandidate.followup_job_id == boundary_in.id,
            )
        )

        assert stale_boundary is not None
        assert stale_boundary.id == original_ids[(boundary_prior.id, boundary_in.id)]
        assert stale_boundary.current_detection_run_id == narrower_run.id
        assert stale_boundary.is_suppressed is True
        assert stale_boundary.suppression_reason is CandidateSuppressionReason.OUT_OF_WINDOW
        assert stale_boundary.suppressed_by_signal_key is None
        assert narrower.candidates_suppressed > 0
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


async def _add_organization(
    session: AsyncSession,
    user_id: UUID,
    slug: str,
) -> Organization:
    organization = Organization(name=slug, slug=f"{slug}-{uuid4()}", created_by_user_id=user_id)
    session.add(organization)
    await session.flush()
    session.add(
        OrganizationMembership(
            organization_id=organization.id,
            user_id=user_id,
            role="owner",
        )
    )
    return organization


async def _add_source(
    session: AsyncSession,
    organization_id: UUID,
    name: str,
) -> SourceSystem:
    source = SourceSystem(
        organization_id=organization_id,
        kind=SourceSystemKind.CSV_UPLOAD,
        name=name,
    )
    session.add(source)
    await session.flush()
    return source


async def _add_customer(
    session: AsyncSession,
    organization_id: UUID,
    label: str,
) -> Customer:
    customer = Customer(
        organization_id=organization_id,
        natural_key_hash=f"{organization_id}:{label}".encode(),
        display_name=label,
        normalized_name=label,
    )
    session.add(customer)
    await session.flush()
    return customer


async def _add_job(
    session: AsyncSession,
    organization_id: UUID,
    source_system_id: UUID,
    customer_id: UUID,
    label: str,
    service_date: date,
    *,
    status: JobStatus = JobStatus.COMPLETED,
    started_at: datetime | None = None,
    equipment_id: UUID | None = None,
) -> Job:
    job = Job(
        organization_id=organization_id,
        source_system_id=source_system_id,
        natural_key_hash=f"{organization_id}:{label}".encode(),
        customer_id=customer_id,
        equipment_id=equipment_id,
        status=status,
        service_date=service_date,
        started_at=started_at,
        currency_code="USD",
    )
    session.add(job)
    await session.flush()
    return job
