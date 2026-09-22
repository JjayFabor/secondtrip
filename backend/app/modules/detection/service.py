"""Detection configuration and run orchestration services."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.detection.defaults import DEFAULT_SIGNAL_DEFINITIONS
from app.modules.detection.generation.runner import generate_candidates
from app.modules.detection.models import (
    DetectionRule,
    DetectionRuleSet,
    DetectionRun,
    DetectionSignalDefinition,
)
from app.modules.detection.schemas import DetectionRunStatus, DetectionTrigger
from app.modules.detection.signals.registry import SIGNAL_REGISTRY
from app.modules.detection.signals.runner import evaluate_and_score_candidates
from app.modules.tasks.control import JobControl
from app.modules.tasks.errors import JobCancelled, PermanentJobError
from app.modules.tasks.service import PostgresJobQueue


async def ensure_default_rule_set(
    session: AsyncSession,
    settings: Settings,
    *,
    organization_id: UUID,
    created_by_user_id: UUID | None,
) -> DetectionRuleSet:
    """Create version 1 exactly once for a new organization."""

    existing = await session.scalar(
        select(DetectionRuleSet).where(
            DetectionRuleSet.organization_id == organization_id,
            DetectionRuleSet.is_active.is_(True),
        )
    )
    if existing is not None:
        return existing

    rule_set = DetectionRuleSet(
        organization_id=organization_id,
        version_number=1,
        name="SecondTrip defaults",
        is_active=True,
        window_days=settings.detection_default_window_days,
        min_score_to_surface=settings.detection_default_min_score_to_surface,
        max_followups_per_job=settings.detection_max_followups_per_job,
        created_by_user_id=created_by_user_id,
    )
    session.add(rule_set)
    await session.flush()
    session.add_all(
        DetectionRule(
            organization_id=organization_id,
            rule_set_id=rule_set.id,
            signal_key=definition.key,
            kind=definition.kind,
            weight=definition.weight,
            params=definition.params,
            sort_order=sort_order,
        )
        for sort_order, definition in enumerate(DEFAULT_SIGNAL_DEFINITIONS, start=10)
    )
    await session.flush()
    return rule_set


async def assert_signal_catalogue(session: AsyncSession) -> None:
    database_keys = set(
        (await session.execute(select(DetectionSignalDefinition.key))).scalars().all()
    )
    registry_keys = set(SIGNAL_REGISTRY)
    if database_keys != registry_keys:
        missing_in_database = sorted(registry_keys - database_keys)
        missing_in_code = sorted(database_keys - registry_keys)
        raise RuntimeError(
            "signal registry and database catalogue differ: "
            f"missing_in_database={missing_in_database}, missing_in_code={missing_in_code}"
        )


async def enqueue_detection_run(
    session: AsyncSession,
    queue: PostgresJobQueue,
    settings: Settings,
    tenant: TenantContext,
    *,
    trigger: DetectionTrigger,
    from_date: date,
    to_date: date,
    import_batch_id: UUID | None = None,
) -> DetectionRun:
    if from_date > to_date:
        raise ValueError("from_date must be on or before to_date")
    rule_set = await ensure_default_rule_set(
        session,
        settings,
        organization_id=tenant.organization_id,
        created_by_user_id=tenant.actor_user_id,
    )
    scope: dict[str, object] = {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
    }
    if import_batch_id is not None:
        scope["import_batch_id"] = str(import_batch_id)
    run = DetectionRun(
        organization_id=tenant.organization_id,
        rule_set_id=rule_set.id,
        trigger=trigger,
        scope=scope,
        status=DetectionRunStatus.QUEUED,
    )
    session.add(run)
    await session.flush()
    background_job = await queue.enqueue(
        session,
        organization_id=tenant.organization_id,
        job_type="detection.run",
        payload={"version": 1, "detection_run_id": str(run.id)},
        idempotency_key=f"detection.run:{run.id}",
        enqueued_by_user_id=tenant.actor_user_id,
        correlation_id=tenant.request_id,
    )
    run.background_job_id = background_job.id
    await session.flush()
    return run


async def execute_detection_run(
    tenant: TenantContext,
    *,
    detection_run_id: UUID,
    control: JobControl,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    try:
        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            run = await _get_run(session, tenant.organization_id, detection_run_id, for_update=True)
            if run.status is DetectionRunStatus.COMPLETED:
                return
            if run.status is DetectionRunStatus.CANCELLED:
                raise JobCancelled
            rule_set = await session.scalar(
                select(DetectionRuleSet).where(
                    DetectionRuleSet.organization_id == tenant.organization_id,
                    DetectionRuleSet.id == run.rule_set_id,
                )
            )
            if rule_set is None:
                raise PermanentJobError("Detection rule set no longer exists.")
            await assert_signal_catalogue(session)
            from_date, to_date = _scope_dates(run.scope)
            run.status = DetectionRunStatus.RUNNING
            run.started_at = run.started_at or datetime.now(UTC)
            run.completed_at = None
            run.error_message = None

        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            run = await _get_run(session, tenant.organization_id, detection_run_id)
            rule_set = await session.scalar(
                select(DetectionRuleSet).where(
                    DetectionRuleSet.organization_id == tenant.organization_id,
                    DetectionRuleSet.id == run.rule_set_id,
                )
            )
            assert rule_set is not None
            generation = await generate_candidates(
                session,
                organization_id=tenant.organization_id,
                rule_set_id=rule_set.id,
                detection_run_id=run.id,
                from_date=from_date,
                to_date=to_date,
                window_days=rule_set.window_days,
                max_followups_per_job=rule_set.max_followups_per_job,
            )
            evaluation = await evaluate_and_score_candidates(
                session,
                organization_id=tenant.organization_id,
                rule_set_id=rule_set.id,
                detection_run_id=run.id,
            )
            run.pairs_evaluated = generation.pairs_evaluated
            run.candidates_created = generation.candidates_created
            run.candidates_updated = generation.candidates_updated
            run.candidates_suppressed = (
                generation.candidates_suppressed + evaluation.candidates_suppressed
            )
            run.status = DetectionRunStatus.COMPLETED
            run.completed_at = datetime.now(UTC)
        await control.checkpoint()
    except JobCancelled:
        await _mark_run_finished(
            session_factory,
            tenant,
            detection_run_id,
            status=DetectionRunStatus.CANCELLED,
        )
        raise
    except Exception as exc:
        await _mark_run_finished(
            session_factory,
            tenant,
            detection_run_id,
            status=DetectionRunStatus.FAILED,
            error_message=type(exc).__name__,
        )
        raise


async def _get_run(
    session: AsyncSession,
    organization_id: UUID,
    detection_run_id: UUID,
    *,
    for_update: bool = False,
) -> DetectionRun:
    statement = select(DetectionRun).where(
        DetectionRun.organization_id == organization_id,
        DetectionRun.id == detection_run_id,
    )
    if for_update:
        statement = statement.with_for_update()
    run = await session.scalar(statement)
    if run is None:
        raise PermanentJobError("Detection run no longer exists.")
    return run


def _scope_dates(scope: dict[str, object]) -> tuple[date, date]:
    try:
        from_date = date.fromisoformat(str(scope["from_date"]))
        to_date = date.fromisoformat(str(scope["to_date"]))
    except (KeyError, ValueError) as exc:
        raise PermanentJobError("Detection run scope is invalid.") from exc
    if from_date > to_date:
        raise PermanentJobError("Detection run scope is invalid.")
    return from_date, to_date


async def _mark_run_finished(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantContext,
    detection_run_id: UUID,
    *,
    status: DetectionRunStatus,
    error_message: str | None = None,
) -> None:
    async with tenant_session(session_factory, tenant) as session:
        run = await _get_run(session, tenant.organization_id, detection_run_id, for_update=True)
        run.status = status
        run.error_message = error_message
        run.completed_at = datetime.now(UTC)
