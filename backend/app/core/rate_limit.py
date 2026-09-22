"""Small Postgres-backed fixed-window limiter for public and invite flows."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import RateLimitExceededError


async def enforce_rate_limit(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Atomically increment a counter and reject the request if it crossed its limit."""
    async with session_factory() as session, session.begin():
        result = await session.execute(
            text(
                "INSERT INTO rate_limit_counters (key, window_start, count, updated_at) "
                "VALUES (:key, now(), 1, now()) "
                "ON CONFLICT (key) DO UPDATE SET "
                "count = CASE "
                "  WHEN rate_limit_counters.window_start <= "
                "       now() - (:window_seconds * interval '1 second') THEN 1 "
                "  ELSE rate_limit_counters.count + 1 END, "
                "window_start = CASE "
                "  WHEN rate_limit_counters.window_start <= "
                "       now() - (:window_seconds * interval '1 second') THEN now() "
                "  ELSE rate_limit_counters.window_start END, "
                "updated_at = now() "
                "RETURNING count"
            ),
            {"key": key, "window_seconds": window_seconds},
        )
        count = int(result.scalar_one())

    if count > limit:
        raise RateLimitExceededError(
            f"Too many requests. Try again in about {timedelta(seconds=window_seconds)}.",
            retry_after=window_seconds,
        )
