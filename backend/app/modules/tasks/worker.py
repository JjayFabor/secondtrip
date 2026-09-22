"""Crash-tolerant in-process worker for the PostgreSQL queue."""

from __future__ import annotations

import asyncio
import os
import random
import socket
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import worker_session
from app.modules.tasks.control import JobControl
from app.modules.tasks.errors import JobCancelled, PermanentJobError
from app.modules.tasks.models import BackgroundJob
from app.modules.tasks.registry import JobRegistry
from app.modules.tasks.repository import BackgroundJobRepository

log = structlog.get_logger(__name__)


class BackgroundWorker:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        registry: JobRegistry,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._settings = settings
        self._worker_id = settings.worker_id or f"{socket.gethostname()}:{os.getpid()}"
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._semaphore = asyncio.Semaphore(settings.worker_concurrency)

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("Background worker already started.")
        self._stop.clear()
        self._task = asyncio.create_task(self.run(), name="secondtrip-worker")

    async def stop(self, *, grace_seconds: float = 25) -> None:
        self._stop.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(self._task), timeout=grace_seconds)
        except TimeoutError:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None

    async def run(self) -> None:
        poll_delay = self._settings.worker_poll_min_seconds
        next_recovery = 0.0
        while not self._stop.is_set():
            try:
                if monotonic() >= next_recovery:
                    await self._recover_stale_jobs()
                    next_recovery = monotonic() + self._settings.worker_stale_after_seconds / 2

                async with worker_session(self._session_factory) as session:
                    jobs = await BackgroundJobRepository(session).claim(
                        worker_id=self._worker_id,
                        batch_size=self._settings.worker_batch_size,
                    )
            except Exception as exc:
                log.error("worker.poll_failed", error_class=type(exc).__name__, exc_info=exc)
                await self._wait_or_stop(self._settings.worker_poll_max_seconds)
                continue
            if not jobs:
                await self._wait_or_stop(poll_delay)
                poll_delay = min(poll_delay * 2, self._settings.worker_poll_max_seconds)
                continue

            poll_delay = self._settings.worker_poll_min_seconds
            await asyncio.gather(*(self._execute_with_slot(job) for job in jobs))

    async def _execute_with_slot(self, job: BackgroundJob) -> None:
        async with self._semaphore:
            try:
                await self._execute(job)
            except Exception as exc:
                # A failed state transition leaves the row processing; stale
                # recovery will safely requeue it without killing the poller.
                log.error(
                    "job.state_transition_failed",
                    job_id=str(job.id),
                    job_type=job.job_type,
                    error_class=type(exc).__name__,
                    exc_info=exc,
                )

    async def _execute(self, job: BackgroundJob) -> None:
        started = monotonic()
        heartbeat = asyncio.create_task(self._heartbeat(job.id), name=f"heartbeat-{job.id}")
        try:
            definition = self._registry.get(job.job_type)
            if definition is None:
                raise PermanentJobError(f"No handler registered for {job.job_type}.")
            if job.organization_id is None:
                raise PermanentJobError("Tenant job has no organization_id.")
            try:
                payload = definition.payload_model.model_validate(job.payload)
            except ValidationError as exc:
                raise PermanentJobError("Job payload failed validation.") from exc

            tenant = TenantContext(
                organization_id=job.organization_id,
                actor_user_id=job.enqueued_by_user_id,
                request_id=job.correlation_id,
            )
            control = JobControl(job_id=job.id, session_factory=self._session_factory)
            async with asyncio.timeout(definition.timeout_seconds):
                await definition.handler(tenant, payload, control)
            async with worker_session(self._session_factory) as session:
                await BackgroundJobRepository(session).mark_completed(
                    job.id, worker_id=self._worker_id
                )
            log.info(
                "job.completed",
                job_id=str(job.id),
                job_type=job.job_type,
                organization_id=str(job.organization_id),
                duration_ms=round((monotonic() - started) * 1000),
            )
        except JobCancelled:
            async with worker_session(self._session_factory) as session:
                await BackgroundJobRepository(session).mark_cancelled(
                    job.id, worker_id=self._worker_id
                )
            log.info("job.cancelled", job_id=str(job.id), job_type=job.job_type)
        except PermanentJobError as exc:
            await self._record_failure(job, exc, permanent=True)
        except Exception as exc:  # the worker boundary owns every handler failure
            await self._record_failure(job, exc, permanent=False)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _record_failure(
        self,
        job: BackgroundJob,
        exc: Exception,
        *,
        permanent: bool,
    ) -> None:
        error = type(exc).__name__
        exhausted = job.attempts >= job.max_attempts
        async with worker_session(self._session_factory) as session:
            repository = BackgroundJobRepository(session)
            if permanent or exhausted:
                await repository.mark_failed(
                    job.id,
                    worker_id=self._worker_id,
                    error=error,
                )
                log.error(
                    "job.failed_permanently",
                    job_id=str(job.id),
                    job_type=job.job_type,
                    error_class=error,
                    exc_info=exc,
                )
                return

            delay = min(
                self._settings.job_backoff_base_seconds * 2 ** (job.attempts - 1),
                self._settings.job_backoff_max_seconds,
            )
            run_at = datetime.now(UTC) + timedelta(seconds=delay + random.uniform(0, delay * 0.25))
            await repository.retry(
                job.id,
                worker_id=self._worker_id,
                error=error,
                run_at=run_at,
            )
        log.warning(
            "job.retrying",
            job_id=str(job.id),
            job_type=job.job_type,
            attempt=job.attempts,
            next_run_at=run_at.isoformat(),
            error_class=error,
        )

    async def _heartbeat(self, job_id: UUID) -> None:
        while True:
            await asyncio.sleep(self._settings.worker_heartbeat_seconds)
            try:
                async with worker_session(self._session_factory) as session:
                    await BackgroundJobRepository(session).heartbeat(
                        job_id, worker_id=self._worker_id
                    )
            except Exception as exc:
                log.warning(
                    "job.heartbeat_failed",
                    job_id=str(job_id),
                    error_class=type(exc).__name__,
                    exc_info=exc,
                )

    async def _recover_stale_jobs(self) -> None:
        stale_before = datetime.now(UTC) - timedelta(
            seconds=self._settings.worker_stale_after_seconds
        )
        async with worker_session(self._session_factory) as session:
            recovered = await BackgroundJobRepository(session).recover_stale(
                stale_before=stale_before
            )
        if recovered:
            log.warning("job.stale_recovered", count=recovered)

    async def _wait_or_stop(self, delay: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=delay)
