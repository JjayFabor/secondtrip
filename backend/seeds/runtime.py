"""Local-only helpers that drive seeds through the production import lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.permissions import OrganizationRole
from app.core.security import hash_password
from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.engine import build_engine, build_session_factory
from app.db.session import tenant_session
from app.modules.billing.entitlements.service import EntitlementService
from app.modules.billing.models import OrganizationSubscription, Plan
from app.modules.detection.reviews import ensure_review_taxonomy
from app.modules.detection.service import ensure_default_rule_set
from app.modules.identity.models import User, UserCredentials, UserStatus
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.models import ImportBatch, ImportRow, ImportStatus
from app.modules.imports.repository import ImportsRepository
from app.modules.imports.service import (
    apply_mapping,
    confirm_upload,
    create_import,
    request_commit,
    request_validation,
    verify_uploaded_object,
)
from app.modules.jobs.models import Job
from app.modules.organizations.models import Organization, OrganizationMembership
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.models import BackgroundJob, BackgroundJobStatus
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker
from app.providers.storage.base import StorageProvider


@dataclass(frozen=True, slots=True)
class SeedPrincipal:
    user_id: UUID
    organization_id: UUID

    def tenant(self, request_id: str) -> TenantContext:
        return TenantContext(
            organization_id=self.organization_id,
            actor_user_id=self.user_id,
            role=OrganizationRole.OWNER,
            request_id=request_id,
        )


@dataclass(frozen=True, slots=True)
class ImportRun:
    batch_id: UUID
    verify_seconds: float
    profile_seconds: float
    validation_seconds: float
    processing_seconds: float
    total_seconds: float
    total_rows: int
    created_jobs: int
    updated_jobs: int
    error_rows: int
    warning_rows: int
    skipped_rows: int
    import_rows: int
    jobs: int


def ensure_local(settings: Settings) -> None:
    if settings.app_env != "local":
        raise RuntimeError("Seed and benchmark commands run only with APP_ENV=local.")


def build_owner_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url_migrations,
        pool_size=2,
        max_overflow=0,
        connect_args={"statement_cache_size": 0},
    )


async def ensure_principal(
    owner_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    email: str,
    password: str,
    organization_name: str,
    organization_slug: str,
    plan_key: str,
) -> SeedPrincipal:
    async with owner_factory() as session, session.begin():
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                full_name="SecondTrip Demo Owner",
                status=UserStatus.ACTIVE.value,
                email_verified_at=datetime.now(UTC),
            )
            session.add(user)
            await session.flush()
            session.add(UserCredentials(user_id=user.id, password_hash=hash_password(password)))
        organization = await session.scalar(
            select(Organization).where(Organization.slug == organization_slug)
        )
        if organization is None:
            organization = Organization(
                name=organization_name,
                slug=organization_slug,
                timezone="America/Chicago",
                currency_code="USD",
                industry_key="hvac",
                created_by_user_id=user.id,
                onboarding_completed_at=datetime.now(UTC),
            )
            session.add(organization)
            await session.flush()
        membership = await session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization.id,
                OrganizationMembership.user_id == user.id,
                OrganizationMembership.revoked_at.is_(None),
            )
        )
        if membership is None:
            session.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=OrganizationRole.OWNER.value,
                )
            )
        plan_id = await session.scalar(select(Plan.id).where(Plan.key == plan_key))
        if plan_id is None:
            raise RuntimeError(f"Plan {plan_key!r} is not seeded; run migrations first.")
        subscription = await session.scalar(
            select(OrganizationSubscription).where(
                OrganizationSubscription.organization_id == organization.id
            )
        )
        if subscription is None:
            session.add(
                OrganizationSubscription(
                    organization_id=organization.id,
                    plan_id=plan_id,
                    status="active",
                    billing_provider="noop",
                )
            )
        else:
            subscription.plan_id = plan_id
            subscription.status = "active"
        await ensure_default_rule_set(
            session,
            settings,
            organization_id=organization.id,
            created_by_user_id=user.id,
        )
        await ensure_review_taxonomy(session, organization_id=organization.id)
        return SeedPrincipal(user.id, organization.id)


async def remove_principal(
    owner_factory: async_sessionmaker[AsyncSession], principal: SeedPrincipal
) -> None:
    parameters = {"organization_id": principal.organization_id}
    async with owner_factory() as session, session.begin():
        # Delete the two high-cardinality dependency chains explicitly. Letting the
        # organization cascade choose its own order first updates every jobs/import_rows
        # cross-reference, even though both sides are about to be removed.
        for table_name in (
            "import_rows",
            "job_notes",
            "job_line_items",
        ):
            await session.execute(
                text(f"DELETE FROM {table_name} WHERE organization_id = :organization_id"),
                parameters,
            )
    async with owner_factory() as session, session.begin():
        for table_name in ("jobs", "import_batches"):
            await session.execute(
                text(f"DELETE FROM {table_name} WHERE organization_id = :organization_id"),
                parameters,
            )
    async with owner_factory() as session, session.begin():
        await session.execute(
            delete(Organization).where(Organization.id == principal.organization_id)
        )
        memberships = await session.scalar(
            select(func.count())
            .select_from(OrganizationMembership)
            .where(OrganizationMembership.user_id == principal.user_id)
        )
        if not memberships:
            await session.execute(delete(User).where(User.id == principal.user_id))


async def wait_for_status(
    factory: async_sessionmaker[AsyncSession],
    tenant: TenantContext,
    batch_id: UUID,
    expected: set[ImportStatus],
    *,
    timeout: float,
) -> ImportBatch:
    async with asyncio.timeout(timeout):
        while True:
            async with tenant_session(factory, tenant) as session:
                batch = await ImportsRepository(session, tenant).get_batch(batch_id)
                if batch is None:
                    raise RuntimeError("Import batch disappeared.")
                if batch.status in expected:
                    return batch
                if batch.status in {ImportStatus.FAILED, ImportStatus.CANCELLED}:
                    reason = batch.failure_reason or "no reason"
                    raise RuntimeError(f"Import ended as {batch.status.value}: {reason}")
            await asyncio.sleep(0.02)


async def run_import(
    settings: Settings,
    principal: SeedPrincipal,
    storage: StorageProvider,
    body: bytes,
    mapping: MappingDocument,
    *,
    original_filename: str,
    timeout: float,
) -> ImportRun:
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    tenant = principal.tenant(f"seed-import:{principal.organization_id}")
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    worker_settings = settings.model_copy(
        update={
            "worker_id": f"seed-worker-{principal.organization_id}",
            "worker_concurrency": 1,
            "worker_batch_size": 5,
            "worker_poll_min_seconds": 0.01,
            "worker_poll_max_seconds": 0.05,
            "worker_heartbeat_seconds": 15,
            "worker_stale_after_seconds": 120,
        }
    )
    worker = BackgroundWorker(
        session_factory=factory,
        registry=build_job_registry(storage, factory, worker_settings),
        settings=worker_settings,
    )
    try:
        async with tenant_session(factory, tenant) as session:
            creation = await create_import(
                session,
                ImportsRepository(session, tenant),
                EntitlementService(session),
                storage,
                settings,
                tenant,
                original_filename=original_filename,
                source_system_id=None,
            )
            storage_key = creation.upload.key
        await storage.upload(storage_key, body, content_type="text/csv")

        started = perf_counter()
        metadata, digest = await verify_uploaded_object(
            storage, storage_key, max_bytes=settings.import_max_file_bytes
        )
        verified_at = perf_counter()
        worker.start()
        async with tenant_session(factory, tenant) as session:
            await confirm_upload(
                session,
                ImportsRepository(session, tenant),
                queue,
                tenant,
                batch_id=creation.batch.id,
                metadata=metadata,
                digest=digest,
                allow_duplicate=False,
            )
        await wait_for_status(
            factory,
            tenant,
            creation.batch.id,
            {ImportStatus.AWAITING_MAPPING},
            timeout=timeout,
        )
        profiled_at = perf_counter()
        async with tenant_session(factory, tenant) as session:
            repository = ImportsRepository(session, tenant)
            await apply_mapping(
                session,
                repository,
                batch_id=creation.batch.id,
                mapping=mapping,
                template_id=None,
            )
            await request_validation(
                session,
                repository,
                queue,
                tenant,
                batch_id=creation.batch.id,
            )
        await wait_for_status(
            factory,
            tenant,
            creation.batch.id,
            {ImportStatus.VALIDATED},
            timeout=timeout,
        )
        validated_at = perf_counter()
        async with tenant_session(factory, tenant) as session:
            await request_commit(
                session,
                ImportsRepository(session, tenant),
                EntitlementService(session),
                queue,
                tenant,
                batch_id=creation.batch.id,
            )
        batch = await wait_for_status(
            factory,
            tenant,
            creation.batch.id,
            {ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS},
            timeout=timeout,
        )
        completed_at = perf_counter()
        async with tenant_session(factory, tenant) as session:
            import_rows = await session.scalar(
                select(func.count())
                .select_from(ImportRow)
                .where(ImportRow.import_batch_id == batch.id)
            )
            jobs = await session.scalar(select(func.count()).select_from(Job))
            failed_jobs = await session.scalar(
                select(func.count())
                .select_from(BackgroundJob)
                .where(
                    BackgroundJob.organization_id == tenant.organization_id,
                    BackgroundJob.status == BackgroundJobStatus.FAILED,
                )
            )
        if failed_jobs:
            raise RuntimeError(f"{failed_jobs} background jobs failed during import.")
        return ImportRun(
            batch_id=batch.id,
            verify_seconds=verified_at - started,
            profile_seconds=profiled_at - verified_at,
            validation_seconds=validated_at - profiled_at,
            processing_seconds=completed_at - validated_at,
            total_seconds=completed_at - started,
            total_rows=batch.total_rows,
            created_jobs=batch.created_jobs,
            updated_jobs=batch.updated_jobs,
            error_rows=batch.error_rows,
            warning_rows=batch.warning_rows,
            skipped_rows=batch.skipped_rows,
            import_rows=int(import_rows or 0),
            jobs=int(jobs or 0),
        )
    finally:
        await worker.stop()
        await engine.dispose()
