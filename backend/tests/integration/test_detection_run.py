from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.customers.models import Customer
from app.modules.detection.models import DetectionRun, ReworkCandidate
from app.modules.detection.schemas import DetectionRunStatus, DetectionTrigger
from app.modules.detection.service import enqueue_detection_run, ensure_default_rule_set
from app.modules.identity.models import User, UserStatus
from app.modules.jobs.models import Job, SourceSystem, SourceSystemKind
from app.modules.jobs.schemas import JobStatus
from app.modules.organizations.models import Organization, OrganizationMembership
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.models import BackgroundJob, BackgroundJobStatus
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker
from app.providers.storage.memory import InMemoryStorageProvider


async def test_queued_detection_run_owns_the_full_lifecycle(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
    settings: Settings,
) -> None:
    async with AsyncSession(owner_engine, expire_on_commit=False) as session, session.begin():
        unique = uuid4()
        user = User(
            email=f"detection-run-{unique}@example.test",
            full_name="Detection Run",
            status=UserStatus.ACTIVE.value,
        )
        session.add(user)
        await session.flush()
        organization = Organization(
            name="Detection Run",
            slug=f"detection-run-{unique}",
            created_by_user_id=user.id,
        )
        session.add(organization)
        await session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
            )
        )
        source = SourceSystem(
            organization_id=organization.id,
            kind=SourceSystemKind.CSV_UPLOAD,
            name="Test source",
        )
        customer = Customer(
            organization_id=organization.id,
            natural_key_hash=b"detection-run-customer",
            display_name="Test Customer",
            normalized_name="test customer",
        )
        session.add_all([source, customer])
        await session.flush()
        session.add_all(
            [
                Job(
                    organization_id=organization.id,
                    source_system_id=source.id,
                    natural_key_hash=b"detection-run-prior",
                    customer_id=customer.id,
                    status=JobStatus.COMPLETED,
                    service_date=date(2026, 8, 1),
                    revenue_amount=100,
                    currency_code="USD",
                ),
                Job(
                    organization_id=organization.id,
                    source_system_id=source.id,
                    natural_key_hash=b"detection-run-followup",
                    customer_id=customer.id,
                    status=JobStatus.COMPLETED,
                    service_date=date(2026, 8, 5),
                    revenue_amount=0,
                    currency_code="USD",
                ),
            ]
        )
        await ensure_default_rule_set(
            session,
            settings,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )

    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    tenant = TenantContext(
        organization_id=organization.id,
        actor_user_id=user.id,
        request_id="detection-run-test",
    )
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    try:
        async with tenant_session(factory, tenant) as session:
            run = await enqueue_detection_run(
                session,
                queue,
                settings,
                tenant,
                trigger=DetectionTrigger.MANUAL,
                from_date=date(2026, 8, 1),
                to_date=date(2026, 8, 31),
            )
            run_id = run.id
            background_job_id = run.background_job_id

        configured = settings.model_copy(
            update={
                "worker_id": f"detection-run-worker-{uuid4()}",
                "worker_concurrency": 1,
                "worker_batch_size": 1,
                "worker_poll_min_seconds": 0.01,
                "worker_poll_max_seconds": 0.05,
                "worker_heartbeat_seconds": 60,
                "worker_stale_after_seconds": 300,
            }
        )
        worker = BackgroundWorker(
            session_factory=factory,
            registry=build_job_registry(InMemoryStorageProvider(), factory, configured),
            settings=configured,
        )
        worker.start()
        try:
            for _ in range(200):
                async with AsyncSession(owner_engine) as session:
                    status = await session.scalar(
                        select(DetectionRun.status).where(DetectionRun.id == run_id)
                    )
                if status is DetectionRunStatus.COMPLETED:
                    break
                await asyncio.sleep(0.02)
            else:
                raise AssertionError("detection run did not complete")
        finally:
            await worker.stop(grace_seconds=2)

        async with AsyncSession(owner_engine) as session:
            persisted_run = await session.get(DetectionRun, run_id)
            background_job = await session.get(BackgroundJob, background_job_id)
            candidates = list(
                (
                    await session.execute(
                        select(ReworkCandidate).where(
                            ReworkCandidate.organization_id == organization.id,
                            ReworkCandidate.current_detection_run_id == run_id,
                        )
                    )
                ).scalars()
            )
        assert persisted_run is not None
        assert persisted_run.status is DetectionRunStatus.COMPLETED
        assert persisted_run.started_at is not None
        assert persisted_run.completed_at is not None
        assert persisted_run.pairs_evaluated == 1
        assert persisted_run.candidates_created == 1
        assert persisted_run.candidates_updated == 0
        assert persisted_run.candidates_suppressed == 0
        assert background_job is not None
        assert background_job.status is BackgroundJobStatus.COMPLETED
        assert len(candidates) == 1
        assert candidates[0].current_normalized_score is not None
    finally:
        async with AsyncSession(owner_engine) as session, session.begin():
            await session.delete(organization)
            await session.delete(user)
