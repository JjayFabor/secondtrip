"""Cooperative cancellation control passed to long-running handlers."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import worker_session
from app.modules.tasks.errors import JobCancelled
from app.modules.tasks.repository import BackgroundJobRepository


class JobControl:
    def __init__(
        self,
        *,
        job_id: UUID,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.job_id = job_id
        self._session_factory = session_factory

    async def checkpoint(self) -> None:
        """Raise at a safe chunk boundary when cancellation was requested."""
        async with worker_session(self._session_factory) as session:
            if await BackgroundJobRepository(session).is_cancel_requested(self.job_id):
                raise JobCancelled
