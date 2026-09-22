"""Alembic environment.

Runs as DATABASE_URL_MIGRATIONS (the owner role) — never DATABASE_URL (the
non-owner, RLS-bound app role). See docs/architecture/02-multi-tenancy.md
§2: migrations must run as the table owner, both because the app role
lacks DDL privileges and because ALTER DEFAULT PRIVILEGES in
infra/neon/bootstrap.sql applies to objects created by the owner role.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.settings import get_settings
from app.db.base import Base

# Import every module's models here as they're built, so `Base.metadata`
# is complete for autogenerate.
from app.modules.audit import models as audit_models
from app.modules.billing import models as billing_models
from app.modules.customers import models as customer_models
from app.modules.detection import models as detection_models
from app.modules.idempotency import models as idempotency_models
from app.modules.identity import models as identity_models
from app.modules.imports import models as import_models
from app.modules.jobs import models as job_models
from app.modules.organizations import models as organization_models
from app.modules.tasks import models as task_models
from app.modules.workforce import models as workforce_models

_MODEL_MODULES = (
    audit_models,
    billing_models,
    customer_models,
    detection_models,
    identity_models,
    idempotency_models,
    import_models,
    job_models,
    organization_models,
    task_models,
    workforce_models,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_migrations)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url_migrations,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
