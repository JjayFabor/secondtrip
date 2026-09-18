"""Async engine — tuned for Neon's PgBouncer transaction pooling.

See docs/architecture/01-system-architecture.md §6. `statement_cache_size=0`
disables asyncpg's server-side prepared-statement cache; without it,
PgBouncer transaction mode intermittently raises "prepared statement
already exists" because a pooled connection is shared across unrelated
transactions that don't share prepared-statement state. Harmless locally
against a direct (non-pooled) connection — always on for consistency.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_seconds,
        echo=settings.db_echo,
        connect_args={
            "statement_cache_size": 0,
            "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
        },
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)
