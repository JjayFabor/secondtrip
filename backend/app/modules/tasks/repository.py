"""PostgreSQL queue persistence and atomic SKIP LOCKED claiming."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.tasks.models import BackgroundJob, BackgroundJobStatus


class BackgroundJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        *,
        organization_id: UUID | None,
        job_type: str,
        payload: dict[str, object],
        priority: int = 100,
        idempotency_key: str | None = None,
        enqueued_by_user_id: UUID | None = None,
        correlation_id: str | None = None,
        max_attempts: int = 5,
        run_at: datetime | None = None,
    ) -> BackgroundJob:
        values: dict[str, object] = {
            "id": new_id(),
            "organization_id": organization_id,
            "job_type": job_type,
            "payload": payload,
            "priority": priority,
            "idempotency_key": idempotency_key,
            "enqueued_by_user_id": enqueued_by_user_id,
            "correlation_id": correlation_id,
            "max_attempts": max_attempts,
        }
        if run_at is not None:
            values["run_at"] = run_at

        statement = insert(BackgroundJob).values(**values)
        if idempotency_key is not None:
            statement = statement.on_conflict_do_nothing(
                index_elements=[BackgroundJob.job_type, BackgroundJob.idempotency_key],
                index_where=(
                    BackgroundJob.idempotency_key.is_not(None)
                    & (BackgroundJob.status != BackgroundJobStatus.FAILED)
                ),
            )
        created = (
            await self._session.execute(statement.returning(BackgroundJob))
        ).scalar_one_or_none()
        if created is not None:
            return created
        return (
            await self._session.execute(
                select(BackgroundJob).where(
                    BackgroundJob.job_type == job_type,
                    BackgroundJob.idempotency_key == idempotency_key,
                    BackgroundJob.status != BackgroundJobStatus.FAILED,
                )
            )
        ).scalar_one()

    async def claim(self, *, worker_id: str, batch_size: int) -> list[BackgroundJob]:
        now = datetime.now(UTC)
        await self._session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.status == BackgroundJobStatus.QUEUED,
                BackgroundJob.cancel_requested.is_(True),
            )
            .values(
                status=BackgroundJobStatus.CANCELLED,
                completed_at=now,
                updated_at=now,
            )
        )
        claimable: Select[tuple[UUID]] = (
            select(BackgroundJob.id)
            .where(
                BackgroundJob.status == BackgroundJobStatus.QUEUED,
                BackgroundJob.run_at <= now,
            )
            .order_by(BackgroundJob.priority, BackgroundJob.run_at, BackgroundJob.id)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        claimed = claimable.cte("claimed")
        statement = (
            update(BackgroundJob)
            .where(BackgroundJob.id.in_(select(claimed.c.id)))
            .values(
                status=BackgroundJobStatus.PROCESSING,
                locked_at=now,
                locked_by=worker_id,
                heartbeat_at=now,
                attempts=BackgroundJob.attempts + 1,
                updated_at=now,
            )
            .returning(BackgroundJob)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def heartbeat(self, job_id: UUID, *, worker_id: str) -> None:
        await self._session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job_id,
                BackgroundJob.status == BackgroundJobStatus.PROCESSING,
                BackgroundJob.locked_by == worker_id,
            )
            .values(heartbeat_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        )

    async def is_cancel_requested(self, job_id: UUID) -> bool:
        return bool(
            (
                await self._session.execute(
                    select(BackgroundJob.cancel_requested).where(BackgroundJob.id == job_id)
                )
            ).scalar_one_or_none()
        )

    async def request_cancel(
        self,
        *,
        organization_id: UUID,
        idempotency_keys: tuple[str, ...],
    ) -> int:
        result = await self._session.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.organization_id == organization_id,
                BackgroundJob.idempotency_key.in_(idempotency_keys),
                BackgroundJob.status.in_(
                    {BackgroundJobStatus.QUEUED, BackgroundJobStatus.PROCESSING}
                ),
            )
            .values(cancel_requested=True, updated_at=datetime.now(UTC))
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    async def mark_completed(self, job_id: UUID, *, worker_id: str) -> None:
        await self._finish(
            job_id,
            worker_id=worker_id,
            status=BackgroundJobStatus.COMPLETED,
        )

    async def mark_cancelled(self, job_id: UUID, *, worker_id: str) -> None:
        await self._finish(
            job_id,
            worker_id=worker_id,
            status=BackgroundJobStatus.CANCELLED,
        )

    async def mark_failed(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        error: str,
    ) -> None:
        await self._finish(
            job_id,
            worker_id=worker_id,
            status=BackgroundJobStatus.FAILED,
            last_error=error,
        )

    async def retry(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        error: str,
        run_at: datetime,
    ) -> None:
        await self._session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id, BackgroundJob.locked_by == worker_id)
            .values(
                status=BackgroundJobStatus.QUEUED,
                run_at=run_at,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                last_error=error,
                updated_at=datetime.now(UTC),
            )
        )

    async def recover_stale(self, *, stale_before: datetime) -> int:
        now = datetime.now(UTC)
        stale_filters = (
            BackgroundJob.status == BackgroundJobStatus.PROCESSING,
            BackgroundJob.heartbeat_at < stale_before,
        )
        failed = await self._session.execute(
            update(BackgroundJob)
            .where(
                *stale_filters,
                BackgroundJob.attempts >= BackgroundJob.max_attempts,
            )
            .values(
                status=BackgroundJobStatus.FAILED,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                completed_at=now,
                last_error="Worker stopped before completing the final attempt.",
                updated_at=now,
            )
        )
        requeued = await self._session.execute(
            update(BackgroundJob)
            .where(
                *stale_filters,
                BackgroundJob.attempts < BackgroundJob.max_attempts,
            )
            .values(
                status=BackgroundJobStatus.QUEUED,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                updated_at=now,
            )
        )
        return int(failed.rowcount + requeued.rowcount)  # type: ignore[attr-defined]

    async def _finish(
        self,
        job_id: UUID,
        *,
        worker_id: str,
        status: BackgroundJobStatus,
        last_error: str | None = None,
    ) -> None:
        await self._session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id, BackgroundJob.locked_by == worker_id)
            .values(
                status=status,
                locked_at=None,
                locked_by=None,
                heartbeat_at=None,
                last_error=last_error,
                completed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
