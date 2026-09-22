from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.errors import EntitlementExceededError
from app.core.permissions import OrganizationRole
from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.billing.entitlements.service import EntitlementService
from app.modules.billing.models import OrganizationEntitlementOverride
from app.modules.customers import models as customer_models
from app.modules.idempotency.service import (
    IdempotencyConflictError,
    claim,
    complete,
    request_digest,
)
from app.modules.identity import models as identity_models  # noqa: F401  # register User FK
from app.modules.imports.errors import DuplicateImportError, InvalidMappingError
from app.modules.imports.mapping.document import FieldMapping, MappingDocument
from app.modules.imports.models import ImportBatch, ImportRow, ImportRowStatus, ImportStatus
from app.modules.imports.processing.processor import process_import
from app.modules.imports.repository import ImportsRepository
from app.modules.imports.service import (
    apply_mapping,
    build_preview,
    confirm_upload,
    create_import,
    request_cancellation,
    request_commit,
    request_validation,
    verify_uploaded_object,
)
from app.modules.jobs import models as job_models
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.models import BackgroundJob, BackgroundJobStatus
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker
from app.providers.storage.memory import InMemoryStorageProvider


@dataclass(frozen=True, slots=True)
class ImportTestContext:
    user_id: UUID
    organization_id: UUID
    factory: async_sessionmaker[AsyncSession]
    tenant: TenantContext


@pytest.fixture
async def import_context(
    owner_engine: AsyncEngine,
    app_engine: AsyncEngine,
) -> AsyncIterator[ImportTestContext]:
    user_id, organization_id = uuid4(), uuid4()
    async with owner_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, status) "
                "VALUES (:id, :email, 'Import Test', 'active')"
            ),
            {"id": user_id, "email": f"import-{user_id}@example.test"},
        )
        await connection.execute(
            text(
                "INSERT INTO organizations (id, name, slug, timezone, created_by_user_id) "
                "VALUES (:id, 'Import Test', :slug, 'America/Chicago', :user_id)"
            ),
            {"id": organization_id, "slug": f"import-{organization_id}", "user_id": user_id},
        )
        await connection.execute(
            text(
                "INSERT INTO organization_memberships (organization_id, user_id, role) "
                "VALUES (:organization_id, :user_id, 'owner')"
            ),
            {"organization_id": organization_id, "user_id": user_id},
        )

    factory = async_sessionmaker(app_engine, expire_on_commit=False, class_=AsyncSession)
    yield ImportTestContext(
        user_id=user_id,
        organization_id=organization_id,
        factory=factory,
        tenant=TenantContext(
            organization_id=organization_id,
            actor_user_id=user_id,
            role=OrganizationRole.OWNER,
            request_id="import-test-request",
        ),
    )

    async with owner_engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": organization_id}
        )
        await connection.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def worker_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={
            "worker_id": f"import-test-worker-{uuid4()}",
            "worker_concurrency": 1,
            "worker_batch_size": 1,
            "worker_poll_min_seconds": 0.01,
            "worker_poll_max_seconds": 0.05,
            "worker_heartbeat_seconds": 60,
            "worker_stale_after_seconds": 300,
        }
    )


async def create_and_upload(
    context: ImportTestContext,
    storage: InMemoryStorageProvider,
    settings: Settings,
    *,
    body: bytes,
    allow_duplicate: bool = False,
) -> tuple[ImportBatch, UUID]:
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    async with tenant_session(context.factory, context.tenant) as session:
        creation = await create_import(
            session,
            ImportsRepository(session, context.tenant),
            EntitlementService(session),
            storage,
            settings,
            context.tenant,
            original_filename="jobs.csv",
            source_system_id=None,
        )
        storage_key = creation.upload.key
        assert creation.upload.max_bytes == 5 * 1024 * 1024
    await storage.upload(storage_key, body, content_type="text/csv")
    metadata, digest = await verify_uploaded_object(
        storage, storage_key, max_bytes=settings.import_max_file_bytes
    )
    async with tenant_session(context.factory, context.tenant) as session:
        batch = await confirm_upload(
            session,
            ImportsRepository(session, context.tenant),
            queue,
            context.tenant,
            batch_id=creation.batch.id,
            metadata=metadata,
            digest=digest,
            allow_duplicate=allow_duplicate,
        )
        job_id = (
            await session.execute(
                select(BackgroundJob.id).where(
                    BackgroundJob.organization_id == context.organization_id,
                    BackgroundJob.job_type == "import.profile",
                    BackgroundJob.idempotency_key == f"import.profile:{creation.batch.id}",
                )
            )
        ).scalar_one()
    return batch, job_id


async def wait_for_batch_status(
    owner_engine: AsyncEngine,
    batch_id: UUID,
    status: ImportStatus,
    *,
    timeout: float = 2,
) -> None:
    async with asyncio.timeout(timeout):
        while True:
            async with owner_engine.connect() as connection:
                current = await connection.scalar(
                    text("SELECT status FROM import_batches WHERE id = :id"), {"id": batch_id}
                )
            if current == status.value:
                return
            await asyncio.sleep(0.01)


async def wait_for_error_report(
    owner_engine: AsyncEngine, batch_id: UUID, *, timeout: float = 2
) -> str:
    async with asyncio.timeout(timeout):
        while True:
            async with owner_engine.connect() as connection:
                key = await connection.scalar(
                    text("SELECT error_report_key FROM import_batches WHERE id = :id"),
                    {"id": batch_id},
                )
            if key is not None:
                return str(key)
            await asyncio.sleep(0.01)


async def prepare_validated_import(
    owner_engine: AsyncEngine,
    settings: Settings,
    context: ImportTestContext,
    storage: InMemoryStorageProvider,
    *,
    body: bytes,
    allow_duplicate: bool = False,
) -> ImportBatch:
    batch, _ = await create_and_upload(
        context,
        storage,
        settings,
        body=body,
        allow_duplicate=allow_duplicate,
    )
    configured = worker_settings(settings)
    worker = BackgroundWorker(
        session_factory=context.factory,
        registry=build_job_registry(storage, context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.AWAITING_MAPPING)
    finally:
        await worker.stop()

    mapping = MappingDocument.model_validate(
        {
            "version": 1,
            "fields": {
                "external_job_id": {"source_column": "Job ID"},
                "customer_external_id": {"source_column": "Customer ID"},
                "customer_name": {"source_column": "Customer"},
                "customer_phone": {"source_column": "Phone"},
                "service_date": {"source_column": "Date"},
                "address_line1": {"source_column": "Address"},
                "postal_code": {"source_column": "Postal"},
                "equipment_serial": {"source_column": "Serial"},
                "technician_name": {"source_column": "Technician"},
                "technician_code": {"source_column": "Tech Code"},
                "service_category": {"source_column": "Category"},
                "summary": {"source_column": "Summary"},
                "revenue_amount": {"source_column": "Revenue"},
                "technician_notes": {"source_column": "Notes"},
                "job_status": {
                    "source_column": "Status",
                    "transform": {"type": "value_map", "map": {"Closed": "completed"}},
                },
            },
        }
    )
    async with tenant_session(context.factory, context.tenant) as session:
        repository = ImportsRepository(session, context.tenant)
        await apply_mapping(
            session,
            repository,
            batch_id=batch.id,
            mapping=mapping,
            template_id=None,
        )
        await request_validation(
            session,
            repository,
            PostgresJobQueue(default_max_attempts=settings.job_max_attempts),
            context.tenant,
            batch_id=batch.id,
        )

    worker = BackgroundWorker(
        session_factory=context.factory,
        registry=build_job_registry(storage, context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.VALIDATED)
    finally:
        await worker.stop()
    return batch


async def test_csv_upload_profiles_previews_and_accepts_mapping(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    csv_body = (
        b"Client Name,Completed Date,Invoice Total,Serial Number\r\n"
        b"Acme LLC,09/18/2026,1234.56,SN-1\r\n"
    )
    batch, job_id = await create_and_upload(import_context, storage, settings, body=csv_body)
    assert batch.status is ImportStatus.UPLOADED

    configured = worker_settings(settings)
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.AWAITING_MAPPING)
    finally:
        await worker.stop()

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        repository = ImportsRepository(session, import_context.tenant)
        preview = await build_preview(repository, batch_id=batch.id)
        assert preview.encoding in {"ascii", "utf-8"}
        assert preview.approximate_row_count == 1
        assert preview.suggested_mapping is not None
        assert preview.suggested_mapping.fields["service_date"].source_column == "Completed Date"
        assert preview.suggested_mapping.fields["customer_name"].source_column == "Client Name"

        mapped = await apply_mapping(
            session,
            repository,
            batch_id=batch.id,
            mapping=preview.suggested_mapping,
            template_id=None,
        )
        assert mapped.mapping is not None
        with pytest.raises(InvalidMappingError, match="unknown source columns"):
            await apply_mapping(
                session,
                repository,
                batch_id=batch.id,
                mapping=MappingDocument(
                    version=1,
                    fields={
                        "service_date": FieldMapping(source_column="Missing Date"),
                        "customer_name": FieldMapping(source_column="Client Name"),
                    },
                ),
                template_id=None,
            )

    async with owner_engine.connect() as connection:
        job_status = await connection.scalar(
            text("SELECT status FROM background_jobs WHERE id = :id"), {"id": job_id}
        )
    assert job_status == BackgroundJobStatus.COMPLETED.value


async def test_duplicate_upload_requires_explicit_confirmation(
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    body = b"Client Name,Completed Date\nAcme,2026-09-18\n"
    first, _ = await create_and_upload(import_context, storage, settings, body=body)

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        second_creation = await create_import(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            storage,
            settings,
            import_context.tenant,
            original_filename="same.csv",
            source_system_id=None,
        )
    await storage.upload(second_creation.upload.key, body, content_type="text/csv")
    metadata, digest = await verify_uploaded_object(
        storage, second_creation.upload.key, max_bytes=settings.import_max_file_bytes
    )
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    with pytest.raises(DuplicateImportError, match=str(first.id)):
        async with tenant_session(import_context.factory, import_context.tenant) as session:
            await confirm_upload(
                session,
                ImportsRepository(session, import_context.tenant),
                queue,
                import_context.tenant,
                batch_id=second_creation.batch.id,
                metadata=metadata,
                digest=digest,
                allow_duplicate=False,
            )

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        duplicate = await confirm_upload(
            session,
            ImportsRepository(session, import_context.tenant),
            queue,
            import_context.tenant,
            batch_id=second_creation.batch.id,
            metadata=metadata,
            digest=digest,
            allow_duplicate=True,
        )
        assert duplicate.duplicate_of_batch_id == first.id


async def test_monthly_import_entitlement_is_enforced_transactionally(
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    for ordinal in range(3):
        async with tenant_session(import_context.factory, import_context.tenant) as session:
            await create_import(
                session,
                ImportsRepository(session, import_context.tenant),
                EntitlementService(session),
                storage,
                settings,
                import_context.tenant,
                original_filename=f"jobs-{ordinal}.csv",
                source_system_id=None,
            )
    with pytest.raises(EntitlementExceededError, match="3 of 3"):
        async with tenant_session(import_context.factory, import_context.tenant) as session:
            await create_import(
                session,
                ImportsRepository(session, import_context.tenant),
                EntitlementService(session),
                storage,
                settings,
                import_context.tenant,
                original_filename="one-too-many.csv",
                source_system_id=None,
            )


async def test_concurrent_import_reservations_cannot_overspend_quota(
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        first = await create_import(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            storage,
            settings,
            import_context.tenant,
            original_filename="first.csv",
            source_system_id=None,
        )

    async def attempt(ordinal: int) -> bool:
        try:
            async with tenant_session(import_context.factory, import_context.tenant) as session:
                await create_import(
                    session,
                    ImportsRepository(session, import_context.tenant),
                    EntitlementService(session),
                    storage,
                    settings,
                    import_context.tenant,
                    original_filename=f"concurrent-{ordinal}.csv",
                    source_system_id=first.batch.source_system_id,
                )
            return True
        except EntitlementExceededError:
            return False

    outcomes = await asyncio.gather(*(attempt(ordinal) for ordinal in range(3)))
    assert sorted(outcomes) == [False, True, True]

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ImportBatch)
            .where(ImportBatch.organization_id == import_context.organization_id)
        )
    assert count == 3


async def test_malformed_csv_marks_batch_and_job_failed(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    batch, job_id = await create_and_upload(
        import_context,
        storage,
        settings,
        body=b'customer,date\n"unterminated,2026-09-18\n',
    )
    configured = worker_settings(settings)
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.FAILED)
    finally:
        await worker.stop()
    async with owner_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT b.failure_reason, j.status AS job_status "
                    "FROM import_batches b JOIN background_jobs j "
                    "ON j.organization_id = b.organization_id "
                    "WHERE b.id = :batch_id AND j.id = :job_id"
                ),
                {"batch_id": batch.id, "job_id": job_id},
            )
        ).one()
    assert "could not be parsed" in row.failure_reason
    assert row.job_status == BackgroundJobStatus.FAILED.value


async def test_validation_persists_every_row_and_generates_safe_error_report(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    body = (
        b"Customer,Date,Revenue,Serial,Status\n"
        b"Acme,2026-09-18,100,SN-1,Closed\n"
        b"Acme,2026-09-18,100,SN-1,Closed\n"
        b",2026-09-18,50,SN-2,Closed\n"
        b"Beta,03/04/2026,75,SN-3,Closed\n"
        b"Estimate,2026-09-18,20,SN-4,Estimate\n"
        b"Credit,2026-09-19,-25,SN-5,Closed\n"
        b"Formula,2026-09-20,=2+2,SN-6,Closed\n"
    )
    batch, _ = await create_and_upload(import_context, storage, settings, body=body)
    configured = worker_settings(settings)
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.AWAITING_MAPPING)
    finally:
        await worker.stop()

    mapping = MappingDocument.model_validate(
        {
            "version": 1,
            "fields": {
                "service_date": {"source_column": "Date"},
                "customer_name": {"source_column": "Customer"},
                "revenue_amount": {"source_column": "Revenue"},
                "equipment_serial": {"source_column": "Serial"},
                "job_status": {
                    "source_column": "Status",
                    "transform": {
                        "type": "value_map",
                        "map": {"Closed": "completed"},
                    },
                },
            },
            "skip_rows_where": [{"column": "Status", "operator": "equals", "value": "Estimate"}],
        }
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        repository = ImportsRepository(session, import_context.tenant)
        await apply_mapping(
            session,
            repository,
            batch_id=batch.id,
            mapping=mapping,
            template_id=None,
        )
        requested = await request_validation(
            session,
            repository,
            PostgresJobQueue(default_max_attempts=settings.job_max_attempts),
            import_context.tenant,
            batch_id=batch.id,
        )
        assert requested.status is ImportStatus.VALIDATING

    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.VALIDATED)
        report_key = await wait_for_error_report(owner_engine, batch.id)
    finally:
        await worker.stop()

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        persisted_batch = await ImportsRepository(session, import_context.tenant).get_batch(
            batch.id
        )
        assert persisted_batch is not None
        assert persisted_batch.total_rows == 7
        assert persisted_batch.processed_rows == 7
        assert persisted_batch.error_rows == 3
        assert persisted_batch.warning_rows == 1
        assert persisted_batch.skipped_rows == 2
        rows = list(
            (
                await session.execute(
                    select(ImportRow)
                    .where(
                        ImportRow.organization_id == import_context.organization_id,
                        ImportRow.import_batch_id == batch.id,
                    )
                    .order_by(ImportRow.row_number)
                )
            )
            .scalars()
            .all()
        )
        assert [row.row_number for row in rows] == list(range(2, 9))
        assert [row.status for row in rows] == [
            ImportRowStatus.PENDING,
            ImportRowStatus.SKIPPED_DUPLICATE,
            ImportRowStatus.ERROR,
            ImportRowStatus.ERROR,
            ImportRowStatus.SKIPPED_FILTERED,
            ImportRowStatus.WARNING,
            ImportRowStatus.ERROR,
        ]
        issue_rows, next_cursor = await ImportsRepository(
            session, import_context.tenant
        ).list_issue_rows(batch.id, cursor=None, limit=2)
        assert len(issue_rows) == 2
        assert next_cursor is not None

    report = b"".join([chunk async for chunk in storage.download(report_key)]).decode()
    assert report.startswith("row_number,status,error_code,field,message,raw_value\r\n")
    assert "'=2+2" in report
    assert "'-25" in report


async def test_queued_validation_can_be_cancelled_without_running(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    batch, _ = await create_and_upload(
        import_context,
        storage,
        settings,
        body=b"Customer,Date\nAcme,2026-09-18\n",
    )
    configured = worker_settings(settings)
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.AWAITING_MAPPING)
    finally:
        await worker.stop()

    mapping = MappingDocument(
        version=1,
        fields={
            "service_date": FieldMapping(source_column="Date"),
            "customer_name": FieldMapping(source_column="Customer"),
        },
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        repository = ImportsRepository(session, import_context.tenant)
        await apply_mapping(
            session,
            repository,
            batch_id=batch.id,
            mapping=mapping,
            template_id=None,
        )
        queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
        await request_validation(
            session,
            repository,
            queue,
            import_context.tenant,
            batch_id=batch.id,
        )
        cancelled = await request_cancellation(
            session,
            repository,
            queue,
            import_context.tenant,
            batch_id=batch.id,
        )
        assert cancelled.status is ImportStatus.CANCELLED
        assert cancelled.cancel_requested_at is not None

    async with owner_engine.connect() as connection:
        cancel_requested = await connection.scalar(
            text(
                "SELECT cancel_requested FROM background_jobs "
                "WHERE organization_id = :organization_id "
                "AND idempotency_key = :idempotency_key"
            ),
            {
                "organization_id": import_context.organization_id,
                "idempotency_key": f"import.validate:{batch.id}",
            },
        )
    assert cancel_requested is True


PROCESSING_CSV = (
    b"Job ID,Customer ID,Customer,Phone,Date,Address,Postal,Serial,Technician,"
    b"Tech Code,Category,Summary,Revenue,Notes,Status\n"
    b"J-100,C-100,Acme LLC,+14155550100,2026-09-17,1 Main St,94105,SN-100,"
    b"Alex Rivera,T-1,Repair,Compressor repair,450.00,Checked pressures,Closed\n"
    b"J-101,C-101,Beta Co,,2026-09-18,2 Oak St,94107,,Morgan Lee,T-2,Maintenance,"
    b"Annual maintenance,125.00,Changed filter,Closed\n"
)


class InterruptAfterFirstChunk:
    def __init__(self) -> None:
        self.checkpoints = 0

    async def checkpoint(self) -> None:
        self.checkpoints += 1
        if self.checkpoints == 3:
            raise RuntimeError("simulated worker interruption")


async def test_commit_processes_entities_and_resumes_from_checkpoint(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    batch = await prepare_validated_import(
        owner_engine,
        settings,
        import_context,
        storage,
        body=PROCESSING_CSV,
    )
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        committed = await request_commit(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            queue,
            import_context.tenant,
            batch_id=batch.id,
        )
        assert committed.status is ImportStatus.QUEUED
        assert committed.processed_rows == 0

    configured = worker_settings(settings).model_copy(update={"import_chunk_size": 1})
    with pytest.raises(RuntimeError, match="simulated worker interruption"):
        await process_import(
            import_context.tenant,
            batch_id=batch.id,
            control=InterruptAfterFirstChunk(),  # type: ignore[arg-type]
            session_factory=import_context.factory,
            settings=configured,
            queue=queue,
        )

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        interrupted = await ImportsRepository(session, import_context.tenant).get_batch(batch.id)
        assert interrupted is not None
        assert interrupted.status is ImportStatus.PROCESSING
        assert interrupted.processed_rows == 1
        assert interrupted.created_jobs == 1

    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, batch.id, ImportStatus.COMPLETED)
    finally:
        await worker.stop()

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        completed = await ImportsRepository(session, import_context.tenant).get_batch(batch.id)
        assert completed is not None
        assert completed.processed_rows == 2
        assert completed.created_jobs == 2
        assert completed.updated_jobs == 0
        assert await session.scalar(
            select(func.count()).select_from(customer_models.Customer)
        ) == 2
        assert await session.scalar(
            select(func.count()).select_from(customer_models.Location)
        ) == 2
        assert await session.scalar(
            select(func.count()).select_from(customer_models.Equipment)
        ) == 1
        assert await session.scalar(select(func.count()).select_from(job_models.Job)) == 2
        assert await session.scalar(select(func.count()).select_from(job_models.JobNote)) == 2
        rows = list(
            (
                await session.execute(
                    select(ImportRow)
                    .where(ImportRow.import_batch_id == batch.id)
                    .order_by(ImportRow.row_number)
                )
            )
            .scalars()
            .all()
        )
        assert all(row.job_id is not None for row in rows)
        assert all(row.status is ImportRowStatus.IMPORTED for row in rows)


async def test_reimport_same_file_creates_no_jobs_and_changed_file_updates(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    configured = worker_settings(settings)
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    first = await prepare_validated_import(
        owner_engine, settings, import_context, storage, body=PROCESSING_CSV
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        await request_commit(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            queue,
            import_context.tenant,
            batch_id=first.id,
        )
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, first.id, ImportStatus.COMPLETED)
    finally:
        await worker.stop()

    second = await prepare_validated_import(
        owner_engine,
        settings,
        import_context,
        storage,
        body=PROCESSING_CSV,
        allow_duplicate=True,
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        await request_commit(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            queue,
            import_context.tenant,
            batch_id=second.id,
        )
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, second.id, ImportStatus.COMPLETED)
    finally:
        await worker.stop()

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        completed = await ImportsRepository(session, import_context.tenant).get_batch(second.id)
        assert completed is not None
        assert completed.created_jobs == 0
        assert completed.updated_jobs == 2
        assert await session.scalar(select(func.count()).select_from(job_models.Job)) == 2
        assert await session.scalar(
            select(func.count()).select_from(customer_models.Customer)
        ) == 2

    changed = PROCESSING_CSV.replace(b"Compressor repair", b"Compressor replacement")
    third = await prepare_validated_import(
        owner_engine, settings, import_context, storage, body=changed
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        await request_commit(
            session,
            ImportsRepository(session, import_context.tenant),
            EntitlementService(session),
            queue,
            import_context.tenant,
            batch_id=third.id,
        )
    worker = BackgroundWorker(
        session_factory=import_context.factory,
        registry=build_job_registry(storage, import_context.factory, configured),
        settings=configured,
    )
    worker.start()
    try:
        await wait_for_batch_status(owner_engine, third.id, ImportStatus.COMPLETED)
    finally:
        await worker.stop()

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        completed = await ImportsRepository(session, import_context.tenant).get_batch(third.id)
        assert completed is not None
        assert completed.created_jobs == 0
        assert completed.updated_jobs == 2
        summary = await session.scalar(
            select(job_models.Job.summary).where(job_models.Job.external_id == "J-100")
        )
        assert summary == "Compressor replacement"


async def test_commit_quota_denial_rolls_back_batch_and_queue(
    owner_engine: AsyncEngine,
    settings: Settings,
    import_context: ImportTestContext,
) -> None:
    storage = InMemoryStorageProvider()
    batch = await prepare_validated_import(
        owner_engine, settings, import_context, storage, body=PROCESSING_CSV
    )
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        session.add(
            OrganizationEntitlementOverride(
                organization_id=import_context.organization_id,
                entitlement_key="jobs_imported",
                limit_value=1,
                reason="test limit",
            )
        )

    with pytest.raises(EntitlementExceededError, match="0 of 1"):
        async with tenant_session(import_context.factory, import_context.tenant) as session:
            await request_commit(
                session,
                ImportsRepository(session, import_context.tenant),
                EntitlementService(session),
                PostgresJobQueue(default_max_attempts=settings.job_max_attempts),
                import_context.tenant,
                batch_id=batch.id,
            )

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        unchanged = await ImportsRepository(session, import_context.tenant).get_batch(batch.id)
        assert unchanged is not None
        assert unchanged.status is ImportStatus.VALIDATED
        process_jobs = await session.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(
                BackgroundJob.organization_id == import_context.organization_id,
                BackgroundJob.job_type == "import.process",
            )
        )
        assert process_jobs == 0


async def test_http_idempotency_replays_and_rejects_key_reuse(
    import_context: ImportTestContext,
) -> None:
    route = "/imports/{batch_id}/commit"
    key = "commit-retry"
    digest = request_digest({"batch_id": "one"})
    async with tenant_session(import_context.factory, import_context.tenant) as session:
        first = await claim(
            session,
            organization_id=import_context.organization_id,
            route=route,
            idempotency_key=key,
            digest=digest,
        )
        assert first.replay_body is None
        complete(first, status_code=202, response_body={"id": "one"})

    async with tenant_session(import_context.factory, import_context.tenant) as session:
        replay = await claim(
            session,
            organization_id=import_context.organization_id,
            route=route,
            idempotency_key=key,
            digest=digest,
        )
        assert replay.replay_status == 202
        assert replay.replay_body == {"id": "one"}

    with pytest.raises(IdempotencyConflictError):
        async with tenant_session(import_context.factory, import_context.tenant) as session:
            await claim(
                session,
                organization_id=import_context.organization_id,
                route=route,
                idempotency_key=key,
                digest=request_digest({"batch_id": "two"}),
            )
