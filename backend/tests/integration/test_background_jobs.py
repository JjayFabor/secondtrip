from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session, worker_session
from app.modules.tasks.control import JobControl
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.models import BackgroundJobStatus
from app.modules.tasks.registry import JobRegistry
from app.modules.tasks.repository import BackgroundJobRepository
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker
from app.providers.storage.memory import InMemoryStorageProvider


@dataclass(frozen=True, slots=True)
class QueueTestContext:
    user_id: UUID
    organization_id: UUID
    factory: async_sessionmaker[AsyncSession]
    tenant: TenantContext


@dataclass(frozen=True, slots=True)
class JobSnapshot:
    status: str
    attempts: int
    run_at: datetime
    last_error: str | None


@pytest.fixture
async def queue_context(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
) -> AsyncIterator[QueueTestContext]:
    user_id, organization_id = uuid4(), uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, status) "
                "VALUES (:id, :email, 'Queue Test', 'active')"
            ),
            {"id": user_id, "email": f"queue-{user_id}@example.test"},
        )
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, slug, created_by_user_id) "
                "VALUES (:id, 'Queue Test', :slug, :user_id)"
            ),
            {"id": organization_id, "slug": f"queue-{organization_id}", "user_id": user_id},
        )
        await connection.execute(
            text(
                "INSERT INTO organization_memberships (organization_id, user_id, role) "
                "VALUES (:organization_id, :user_id, 'owner')"
            ),
            {"organization_id": organization_id, "user_id": user_id},
        )

    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    yield QueueTestContext(
        user_id=user_id,
        organization_id=organization_id,
        factory=factory,
        tenant=TenantContext(organization_id=organization_id, actor_user_id=user_id),
    )

    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM organizations WHERE id = :id"),
            {"id": organization_id},
        )
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


async def test_queue_enqueue_is_idempotent_and_worker_claim_is_cross_tenant(
    owner_engine: AsyncEngine,
    queue_context: QueueTestContext,
) -> None:
    organization_id = queue_context.organization_id
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        first = await BackgroundJobRepository(session).enqueue(
            organization_id=organization_id,
            job_type="storage.cleanup",
            payload={"key": f"orgs/{organization_id}/imports/test/source.csv"},
            idempotency_key=f"cleanup:{organization_id}",
        )
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        second = await BackgroundJobRepository(session).enqueue(
            organization_id=organization_id,
            job_type="storage.cleanup",
            payload={"key": f"orgs/{organization_id}/imports/test/source.csv"},
            idempotency_key=f"cleanup:{organization_id}",
        )
    assert second.id == first.id

    async with worker_session(queue_context.factory) as session:
        claimed = await BackgroundJobRepository(session).claim(
            worker_id="test-worker",
            batch_size=5,
        )
    assert [job.id for job in claimed] == [first.id]
    assert claimed[0].status is BackgroundJobStatus.PROCESSING
    assert claimed[0].attempts == 1

    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE background_jobs SET max_attempts = 1, "
                "heartbeat_at = now() - interval '5 minutes' WHERE id = :id"
            ),
            {"id": first.id},
        )
    async with worker_session(queue_context.factory) as session:
        recovered = await BackgroundJobRepository(session).recover_stale(
            stale_before=datetime.now(UTC) - timedelta(minutes=2)
        )
    assert recovered >= 1
    async with owner_engine.connect() as connection:
        stale_status = (
            await connection.execute(
                text("SELECT status FROM background_jobs WHERE id = :id"),
                {"id": first.id},
            )
        ).scalar_one()
    assert stale_status == BackgroundJobStatus.FAILED.value

    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        cancelled = await BackgroundJobRepository(session).enqueue(
            organization_id=organization_id,
            job_type="storage.cleanup",
            payload={"key": f"orgs/{organization_id}/imports/cancel/source.csv"},
            idempotency_key=f"cleanup-cancel:{organization_id}",
        )
        await session.execute(
            text("UPDATE background_jobs SET cancel_requested = true WHERE id = :id"),
            {"id": cancelled.id},
        )
    async with worker_session(queue_context.factory) as session:
        assert (
            await BackgroundJobRepository(session).claim(worker_id="test-worker", batch_size=5)
            == []
        )
    async with owner_engine.connect() as connection:
        cancelled_status = (
            await connection.execute(
                text("SELECT status FROM background_jobs WHERE id = :id"),
                {"id": cancelled.id},
            )
        ).scalar_one()
    assert cancelled_status == BackgroundJobStatus.CANCELLED.value


async def test_concurrent_workers_claim_disjoint_batches_with_skip_locked(
    queue_context: QueueTestContext,
) -> None:
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        repository = BackgroundJobRepository(session)
        expected_ids = {
            (
                await repository.enqueue(
                    organization_id=queue_context.organization_id,
                    job_type="test.concurrent",
                    payload={"ordinal": ordinal},
                    idempotency_key=f"concurrent:{queue_context.organization_id}:{ordinal}",
                )
            ).id
            for ordinal in range(10)
        }

    release = asyncio.Event()
    worker_a_claimed = asyncio.Event()
    worker_b_claimed = asyncio.Event()

    async def claim_and_hold(worker_id: str, claimed_event: asyncio.Event) -> set[UUID]:
        async with worker_session(queue_context.factory) as session:
            jobs = await BackgroundJobRepository(session).claim(
                worker_id=worker_id,
                batch_size=5,
            )
            claimed_event.set()
            await release.wait()
            return {job.id for job in jobs}

    task_a = asyncio.create_task(claim_and_hold("worker-a", worker_a_claimed))
    await asyncio.wait_for(worker_a_claimed.wait(), timeout=2)
    task_b = asyncio.create_task(claim_and_hold("worker-b", worker_b_claimed))
    await asyncio.wait_for(worker_b_claimed.wait(), timeout=2)
    release.set()
    claimed_a, claimed_b = await asyncio.gather(task_a, task_b)

    assert len(claimed_a) == 5
    assert len(claimed_b) == 5
    assert claimed_a.isdisjoint(claimed_b)
    assert claimed_a | claimed_b == expected_ids


async def test_transactional_enqueue_rolls_back_with_owning_state(
    queue_context: QueueTestContext,
) -> None:
    idempotency_key = f"rollback:{queue_context.organization_id}"
    source_name = f"rollback-{queue_context.organization_id}"
    queue = PostgresJobQueue(default_max_attempts=5)

    with pytest.raises(RuntimeError, match="force rollback"):
        async with tenant_session(queue_context.factory, queue_context.tenant) as session:
            await session.execute(
                text(
                    "INSERT INTO source_systems (organization_id, kind, name) "
                    "VALUES (:organization_id, 'csv_upload', :name)"
                ),
                {
                    "organization_id": queue_context.organization_id,
                    "name": source_name,
                },
            )
            await queue.enqueue(
                session,
                organization_id=queue_context.organization_id,
                job_type="test.rollback",
                payload={"state": "must-not-commit"},
                idempotency_key=idempotency_key,
            )
            raise RuntimeError("force rollback")

    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        job_count = (
            await session.execute(
                text(
                    "SELECT count(*) FROM background_jobs WHERE idempotency_key = :idempotency_key"
                ),
                {"idempotency_key": idempotency_key},
            )
        ).scalar_one()
        source_count = (
            await session.execute(
                text("SELECT count(*) FROM source_systems WHERE name = :name"),
                {"name": source_name},
            )
        ).scalar_one()
    assert job_count == 0
    assert source_count == 0


def _worker_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "worker_id": f"test-worker-{uuid4()}",
            "worker_concurrency": 2,
            "worker_batch_size": 5,
            "worker_poll_min_seconds": 0.01,
            "worker_poll_max_seconds": 0.05,
            "worker_heartbeat_seconds": 60,
            "worker_stale_after_seconds": 300,
            "job_backoff_base_seconds": 30,
            "job_backoff_max_seconds": 30,
        }
    )


async def _wait_for_job(
    owner_engine: AsyncEngine,
    job_id: UUID,
    *,
    status: BackgroundJobStatus,
    minimum_attempts: int = 0,
    timeout: float = 2,
) -> JobSnapshot:
    async def read() -> JobSnapshot | None:
        async with owner_engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT status, attempts, run_at, last_error "
                        "FROM background_jobs WHERE id = :id"
                    ),
                    {"id": job_id},
                )
            ).one_or_none()
        if row is None or row.status != status.value or row.attempts < minimum_attempts:
            return None
        return JobSnapshot(
            status=row.status,
            attempts=row.attempts,
            run_at=row.run_at,
            last_error=row.last_error,
        )

    async with asyncio.timeout(timeout):
        while (snapshot := await read()) is None:
            await asyncio.sleep(0.01)
    return snapshot


class EmptyPayload(BaseModel):
    pass


async def test_worker_rehydrates_tenant_context_and_completes(
    owner_engine: AsyncEngine,
    settings: Settings,
    queue_context: QueueTestContext,
) -> None:
    observed: list[TenantContext] = []
    registry = JobRegistry()

    async def succeed(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        del payload
        await control.checkpoint()
        observed.append(tenant)

    registry.register(
        "test.success",
        payload_model=EmptyPayload,
        handler=succeed,
        timeout_seconds=1,
    )
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        job = await BackgroundJobRepository(session).enqueue(
            organization_id=queue_context.organization_id,
            job_type="test.success",
            payload={},
            enqueued_by_user_id=queue_context.user_id,
            correlation_id="queue-correlation-id",
        )

    worker = BackgroundWorker(
        session_factory=queue_context.factory,
        registry=registry,
        settings=_worker_settings(settings),
    )
    worker.start()
    try:
        completed = await _wait_for_job(
            owner_engine,
            job.id,
            status=BackgroundJobStatus.COMPLETED,
        )
    finally:
        await worker.stop(grace_seconds=2)

    assert completed.attempts == 1
    assert observed == [
        TenantContext(
            organization_id=queue_context.organization_id,
            actor_user_id=queue_context.user_id,
            request_id="queue-correlation-id",
        )
    ]


async def test_worker_retries_transient_failures_and_stops_permanent_ones(
    owner_engine: AsyncEngine,
    settings: Settings,
    queue_context: QueueTestContext,
) -> None:
    registry = JobRegistry()

    async def fail(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        del tenant, payload, control
        raise RuntimeError("sensitive provider response must not be persisted")

    async def hang(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        del tenant, payload, control
        await asyncio.sleep(1)

    registry.register(
        "test.retry",
        payload_model=EmptyPayload,
        handler=fail,
        timeout_seconds=1,
    )
    registry.register(
        "test.timeout",
        payload_model=EmptyPayload,
        handler=hang,
        timeout_seconds=0.02,
    )
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        repository = BackgroundJobRepository(session)
        retry_job = await repository.enqueue(
            organization_id=queue_context.organization_id,
            job_type="test.retry",
            payload={},
            max_attempts=2,
        )
        exhausted_job = await repository.enqueue(
            organization_id=queue_context.organization_id,
            job_type="test.retry",
            payload={},
            max_attempts=1,
        )
        timeout_job = await repository.enqueue(
            organization_id=queue_context.organization_id,
            job_type="test.timeout",
            payload={},
            max_attempts=1,
        )

    started_at = datetime.now(UTC)
    worker = BackgroundWorker(
        session_factory=queue_context.factory,
        registry=registry,
        settings=_worker_settings(settings),
    )
    worker.start()
    try:
        retry = await _wait_for_job(
            owner_engine,
            retry_job.id,
            status=BackgroundJobStatus.QUEUED,
            minimum_attempts=1,
        )
        exhausted = await _wait_for_job(
            owner_engine,
            exhausted_job.id,
            status=BackgroundJobStatus.FAILED,
        )
        timed_out = await _wait_for_job(
            owner_engine,
            timeout_job.id,
            status=BackgroundJobStatus.FAILED,
        )
    finally:
        await worker.stop(grace_seconds=2)

    assert retry.attempts == 1
    assert started_at + timedelta(seconds=30) <= retry.run_at
    assert retry.run_at <= started_at + timedelta(seconds=38)
    assert retry.last_error == "RuntimeError"
    assert exhausted.attempts == 1
    assert exhausted.last_error == "RuntimeError"
    assert timed_out.attempts == 1
    assert timed_out.last_error == "TimeoutError"


async def test_invalid_payload_fails_once_without_retry(
    owner_engine: AsyncEngine,
    settings: Settings,
    queue_context: QueueTestContext,
) -> None:
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        job = await BackgroundJobRepository(session).enqueue(
            organization_id=queue_context.organization_id,
            job_type="storage.cleanup",
            payload={"key": "../cross-tenant.csv"},
            max_attempts=5,
        )

    worker = BackgroundWorker(
        session_factory=queue_context.factory,
        registry=build_job_registry(
            InMemoryStorageProvider(), queue_context.factory, _worker_settings(settings)
        ),
        settings=_worker_settings(settings),
    )
    worker.start()
    try:
        failed = await _wait_for_job(
            owner_engine,
            job.id,
            status=BackgroundJobStatus.FAILED,
        )
    finally:
        await worker.stop(grace_seconds=2)

    assert failed.attempts == 1
    assert failed.last_error == "PermanentJobError"


async def test_in_flight_job_cancels_cooperatively_during_graceful_shutdown(
    owner_engine: AsyncEngine,
    settings: Settings,
    queue_context: QueueTestContext,
) -> None:
    started = asyncio.Event()
    registry = JobRegistry()

    async def run_until_cancelled(
        tenant: TenantContext,
        payload: BaseModel,
        control: JobControl,
    ) -> None:
        del tenant, payload
        started.set()
        while True:
            await control.checkpoint()
            await asyncio.sleep(0.01)

    registry.register(
        "test.cancellable",
        payload_model=EmptyPayload,
        handler=run_until_cancelled,
        timeout_seconds=10,
    )
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        job = await BackgroundJobRepository(session).enqueue(
            organization_id=queue_context.organization_id,
            job_type="test.cancellable",
            payload={},
        )

    worker = BackgroundWorker(
        session_factory=queue_context.factory,
        registry=registry,
        settings=_worker_settings(settings),
    )
    worker.start()
    await asyncio.wait_for(started.wait(), timeout=2)
    async with tenant_session(queue_context.factory, queue_context.tenant) as session:
        await session.execute(
            text("UPDATE background_jobs SET cancel_requested = true WHERE id = :id"),
            {"id": job.id},
        )
    await worker.stop(grace_seconds=2)

    cancelled = await _wait_for_job(
        owner_engine,
        job.id,
        status=BackgroundJobStatus.CANCELLED,
    )
    assert cancelled.attempts == 1
