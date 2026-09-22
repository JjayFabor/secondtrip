"""Composition root — builds the engine/session factory and every
provider, storing them on app.state. This is the ONLY place a concrete
provider class is constructed; everything else depends on the protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.db.engine import build_engine, build_session_factory
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker
from app.providers.billing.base import BillingProvider
from app.providers.billing.noop import NoopBillingProvider
from app.providers.email.base import EmailProvider
from app.providers.email.console import ConsoleEmailProvider
from app.providers.email.resend import ResendEmailProvider
from app.providers.storage.base import StorageProvider
from app.providers.storage.local import LocalStorageProvider
from app.providers.storage.memory import InMemoryStorageProvider
from app.providers.storage.r2 import R2StorageProvider


@dataclass(slots=True)
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    email_provider: EmailProvider
    billing_provider: BillingProvider
    storage_provider: StorageProvider
    job_queue: PostgresJobQueue
    worker: BackgroundWorker


def build_email_provider(settings: Settings) -> EmailProvider:
    if settings.email_provider == "resend":
        assert settings.email_api_key is not None  # enforced by Settings validation
        return ResendEmailProvider(
            api_key=settings.email_api_key,
            from_address=settings.email_from_address,
            from_name=settings.email_from_name,
        )
    return ConsoleEmailProvider()


def build_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_provider == "memory":
        return InMemoryStorageProvider()
    if settings.storage_provider == "local":
        return LocalStorageProvider(
            root=Path(settings.storage_local_path),
            app_secret=settings.app_secret,
            base_url=settings.app_url,
        )
    assert settings.storage_bucket is not None
    assert settings.storage_endpoint_url is not None
    assert settings.storage_access_key_id is not None
    assert settings.storage_secret_access_key is not None
    return R2StorageProvider(
        bucket=settings.storage_bucket,
        endpoint_url=settings.storage_endpoint_url,
        access_key_id=settings.storage_access_key_id,
        secret_access_key=settings.storage_secret_access_key,
        region=settings.storage_region,
    )


def build_app_state(settings: Settings) -> AppState:
    engine = build_engine(settings)
    session_factory = build_session_factory(engine)
    storage_provider = build_storage_provider(settings)
    return AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        email_provider=build_email_provider(settings),
        billing_provider=NoopBillingProvider(),
        storage_provider=storage_provider,
        job_queue=PostgresJobQueue(default_max_attempts=settings.job_max_attempts),
        worker=BackgroundWorker(
            session_factory=session_factory,
            registry=build_job_registry(storage_provider, session_factory, settings),
            settings=settings,
        ),
    )


def get_app_state(request: Request) -> AppState:
    """The one place a FastAPI request pulls AppState off app.state.

    Lives here rather than under app/api/ because every module's own
    dependency file (identity/deps.py, organizations/deps.py, ...) needs
    it, and "modules never import api" (see 01-system-architecture.md
    §5 and pyproject.toml's import-linter contracts) would make that a
    layering violation if it lived in app.api instead. composition.py
    already sits below modules in the dependency graph, same as
    core/db/providers.
    """
    # request.app.state is a generic Starlette State object typed as Any
    # — cast rather than suppress, so a genuinely wrong runtime type
    # still fails loudly the first time something dereferences a
    # missing attribute.
    return cast(AppState, request.app.state.app_state)
