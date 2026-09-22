"""Transactional enqueue boundary used by domain services."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.tasks.models import BackgroundJob
from app.modules.tasks.repository import BackgroundJobRepository


class PostgresJobQueue:
    def __init__(self, *, default_max_attempts: int) -> None:
        self._default_max_attempts = default_max_attempts

    async def enqueue(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID | None,
        job_type: str,
        payload: dict[str, object],
        priority: int = 100,
        idempotency_key: str | None = None,
        enqueued_by_user_id: UUID | None = None,
        correlation_id: str | None = None,
        max_attempts: int | None = None,
        run_at: datetime | None = None,
    ) -> BackgroundJob:
        """Enqueue on the caller's session so domain state and work commit together."""
        return await BackgroundJobRepository(session).enqueue(
            organization_id=organization_id,
            job_type=job_type,
            payload=payload,
            priority=priority,
            idempotency_key=idempotency_key,
            enqueued_by_user_id=enqueued_by_user_id,
            correlation_id=correlation_id,
            max_attempts=max_attempts or self._default_max_attempts,
            run_at=run_at,
        )

    async def request_cancel(
        self,
        session: AsyncSession,
        *,
        organization_id: UUID,
        idempotency_keys: tuple[str, ...],
    ) -> int:
        return await BackgroundJobRepository(session).request_cancel(
            organization_id=organization_id,
            idempotency_keys=idempotency_keys,
        )
