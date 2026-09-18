"""Composition root — builds engine/session factory and stores them on
app.state. Provider wiring (AI, storage, email, billing) joins this file
as each provider is built; there are none yet in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import build_engine, build_session_factory


@dataclass(slots=True)
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


def build_app_state(settings: Settings) -> AppState:
    engine = build_engine(settings)
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=build_session_factory(engine),
    )
