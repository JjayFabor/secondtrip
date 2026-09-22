"""Background handlers for import profiling, validation, and issue reports."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import BinaryIO
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.models import ImportRow, ImportRowStatus, ImportStatus
from app.modules.imports.normalization.dates import infer_date_order
from app.modules.imports.normalization.records import serialize_source_record
from app.modules.imports.processing.reader import CsvReaderLimits, CsvReadError, StagedCsv
from app.modules.imports.processing.validator import RowValidation, serialize_issues, validate_row
from app.modules.imports.profiling import ProfileLimits, ProfilingError, profile_csv
from app.modules.imports.reporting.error_report import ErrorReportWriter
from app.modules.imports.repository import ImportsRepository
from app.modules.organizations.service import get_organization_timezone
from app.modules.tasks.control import JobControl
from app.modules.tasks.errors import JobCancelled, PermanentJobError
from app.modules.tasks.service import PostgresJobQueue
from app.providers.storage.base import StorageProvider
from app.providers.storage.keys import import_error_key


async def profile_import(
    tenant: TenantContext,
    *,
    batch_id: UUID,
    control: JobControl,
    storage: StorageProvider,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    await control.checkpoint()
    async with tenant_session(session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id, for_update=True)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        if batch.status is ImportStatus.AWAITING_MAPPING:
            return
        if batch.status not in {ImportStatus.UPLOADED, ImportStatus.PROFILING}:
            raise PermanentJobError("Import batch is not ready for profiling.")
        if batch.storage_key is None:
            raise PermanentJobError("Import batch has no source object.")
        batch.status = ImportStatus.PROFILING
        storage_key = batch.storage_key

    try:
        profile = await profile_csv(
            storage.download(storage_key),
            ProfileLimits(
                max_file_bytes=settings.import_max_file_bytes,
                max_rows=settings.import_max_rows,
                max_field_bytes=settings.import_max_field_bytes,
                max_columns=settings.import_max_columns,
            ),
        )
    except (ProfilingError, FileNotFoundError, KeyError) as exc:
        async with tenant_session(session_factory, tenant) as session:
            repository = ImportsRepository(session, tenant)
            batch = await repository.get_batch(batch_id, for_update=True)
            if batch is not None:
                batch.status = ImportStatus.FAILED
                batch.failure_reason = str(exc)
        raise PermanentJobError("Import profiling failed.") from exc

    await control.checkpoint()
    async with tenant_session(session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id, for_update=True)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        if batch.status is ImportStatus.AWAITING_MAPPING:
            return
        if batch.status is ImportStatus.CANCELLED:
            raise JobCancelled
        if batch.status is not ImportStatus.PROFILING:
            raise PermanentJobError("Import batch changed state during profiling.")
        batch.encoding = profile.encoding
        batch.delimiter = profile.delimiter
        batch.has_header = profile.has_header
        batch.detected_columns = [
            {
                "index": column.ordinal,
                "name": column.name,
                "sample_values": list(column.sample_values),
                "inferred_type": column.inferred_type.value,
            }
            for column in profile.columns
        ]
        batch.sample_rows = [dict(row) for row in profile.sample_rows]
        batch.profile_issues = [
            {
                "code": issue.code.value,
                "severity": issue.severity.value,
                "message": issue.message,
                "field": issue.field,
                "raw_value": issue.raw_value,
            }
            for issue in profile.issues
        ]
        batch.total_rows = profile.approximate_row_count
        batch.file_size_bytes = profile.file_size_bytes
        batch.failure_reason = None
        batch.status = ImportStatus.AWAITING_MAPPING


async def _mark_validation_cancelled(
    session_factory: async_sessionmaker[AsyncSession], tenant: TenantContext, batch_id: UUID
) -> None:
    async with tenant_session(session_factory, tenant) as session:
        batch = await ImportsRepository(session, tenant).get_batch(batch_id, for_update=True)
        if batch is not None and batch.status is ImportStatus.VALIDATING:
            batch.status = ImportStatus.CANCELLED
            batch.completed_at = datetime.now(UTC)


async def _mark_validation_failed(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantContext,
    batch_id: UUID,
    reason: str,
) -> None:
    async with tenant_session(session_factory, tenant) as session:
        batch = await ImportsRepository(session, tenant).get_batch(batch_id, for_update=True)
        if batch is not None and batch.status is ImportStatus.VALIDATING:
            batch.status = ImportStatus.FAILED
            batch.failure_reason = reason[:1000]
            batch.completed_at = datetime.now(UTC)


def _duplicate(validation: RowValidation) -> RowValidation:
    issue = ImportIssue(
        code=IssueCode.DUPLICATE_ROW_IN_FILE,
        severity=IssueSeverity.INFO,
        message="An identical row already appeared in this file.",
    )
    return replace(
        validation,
        status=ImportRowStatus.SKIPPED_DUPLICATE,
        issues=(*validation.issues, issue),
        source_record=None,
    )


async def _persist_validation_chunk(
    session_factory: async_sessionmaker[AsyncSession],
    tenant: TenantContext,
    batch_id: UUID,
    validations: list[RowValidation],
) -> int:
    async with tenant_session(session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id, for_update=True)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        if batch.status is ImportStatus.CANCELLED:
            raise JobCancelled
        if batch.status is not ImportStatus.VALIDATING:
            raise PermanentJobError("Import batch changed state during validation.")

        existing = await repository.existing_row_hashes(
            batch_id, [validation.row_hash for validation in validations]
        )
        seen_in_chunk: set[bytes] = set()
        persisted: list[ImportRow] = []
        warning_rows = 0
        error_rows = 0
        skipped_rows = 0
        issue_rows = 0
        for item in validations:
            if item.row_hash in existing or item.row_hash in seen_in_chunk:
                item = _duplicate(item)
            seen_in_chunk.add(item.row_hash)
            if item.status is ImportRowStatus.WARNING:
                warning_rows += 1
            elif item.status is ImportRowStatus.ERROR:
                error_rows += 1
            elif item.status in {
                ImportRowStatus.SKIPPED_DUPLICATE,
                ImportRowStatus.SKIPPED_FILTERED,
            }:
                skipped_rows += 1
            if item.issues:
                issue_rows += 1
            persisted.append(
                ImportRow(
                    organization_id=tenant.organization_id,
                    import_batch_id=batch_id,
                    row_number=item.row_number,
                    raw_data=item.raw_data,
                    normalized_data=(
                        serialize_source_record(item.source_record)
                        if item.source_record is not None
                        else None
                    ),
                    row_hash=item.row_hash,
                    status=item.status,
                    issues=serialize_issues(item.issues),
                )
            )
        await repository.add_rows(persisted)
        batch.processed_rows += len(persisted)
        batch.warning_rows += warning_rows
        batch.error_rows += error_rows
        batch.skipped_rows += skipped_rows
        return issue_rows


async def validate_import(
    tenant: TenantContext,
    *,
    batch_id: UUID,
    control: JobControl,
    storage: StorageProvider,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    staged: StagedCsv | None = None
    try:
        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            repository = ImportsRepository(session, tenant)
            batch = await repository.get_batch(batch_id, for_update=True)
            if batch is None:
                raise PermanentJobError("Import batch no longer exists.")
            if batch.status is ImportStatus.VALIDATED:
                return
            if batch.status is ImportStatus.CANCELLED:
                raise JobCancelled
            if batch.status is not ImportStatus.VALIDATING:
                raise PermanentJobError("Import batch is not ready for validation.")
            if (
                batch.storage_key is None
                or batch.encoding is None
                or batch.delimiter is None
                or batch.has_header is None
                or batch.detected_columns is None
                or batch.mapping is None
            ):
                raise PermanentJobError("Import profile or mapping is incomplete.")
            storage_key = batch.storage_key
            encoding = batch.encoding
            delimiter = batch.delimiter
            has_header = batch.has_header
            columns = tuple(str(item["name"]) for item in batch.detected_columns)
            mapping = MappingDocument.model_validate(batch.mapping)
            source_system_id = batch.source_system_id
            timezone = await get_organization_timezone(session, tenant.organization_id)
            await repository.clear_validation_rows(batch_id)
            batch.processed_rows = 0
            batch.warning_rows = 0
            batch.error_rows = 0
            batch.skipped_rows = 0
            batch.error_report_key = None
            batch.failure_reason = None

        limits = CsvReaderLimits(
            max_file_bytes=settings.import_max_file_bytes,
            max_rows=settings.import_max_rows,
            max_field_bytes=settings.import_max_field_bytes,
            max_columns=settings.import_max_columns,
        )
        staged = await StagedCsv.create(
            storage.download(storage_key),
            encoding=encoding,
            delimiter=delimiter,
            has_header=has_header,
            columns=columns,
            limits=limits,
        )
        service_date_column = mapping.fields["service_date"].source_column
        date_order = infer_date_order(staged.sample_column(service_date_column, limit=200))

        chunk: list[RowValidation] = []
        issue_rows = 0
        total_rows = 0
        for parsed in staged.rows():
            chunk.append(
                validate_row(
                    parsed,
                    mapping,
                    organization_id=tenant.organization_id,
                    source_system_id=source_system_id,
                    organization_timezone=timezone,
                    date_order=date_order,
                    max_field_bytes=settings.import_max_field_bytes,
                )
            )
            total_rows += 1
            if len(chunk) >= settings.import_chunk_size:
                await control.checkpoint()
                issue_rows += await _persist_validation_chunk(
                    session_factory, tenant, batch_id, chunk
                )
                chunk = []
        if chunk:
            await control.checkpoint()
            issue_rows += await _persist_validation_chunk(session_factory, tenant, batch_id, chunk)

        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            repository = ImportsRepository(session, tenant)
            batch = await repository.get_batch(batch_id, for_update=True)
            if batch is None:
                raise PermanentJobError("Import batch no longer exists.")
            if batch.status is ImportStatus.CANCELLED:
                raise JobCancelled
            if batch.status is not ImportStatus.VALIDATING:
                raise PermanentJobError("Import batch changed state during validation.")
            batch.total_rows = total_rows
            batch.processed_rows = total_rows
            batch.status = ImportStatus.VALIDATED
            batch.failure_reason = None
            if issue_rows:
                await PostgresJobQueue(default_max_attempts=settings.job_max_attempts).enqueue(
                    session,
                    organization_id=tenant.organization_id,
                    job_type="import.error_report",
                    payload={"batch_id": str(batch.id), "version": 1},
                    priority=50,
                    idempotency_key=f"import.error_report:{batch.id}",
                    enqueued_by_user_id=tenant.actor_user_id,
                    correlation_id=tenant.request_id,
                )
    except JobCancelled:
        await _mark_validation_cancelled(session_factory, tenant, batch_id)
        raise
    except (CsvReadError, ValueError, FileNotFoundError, KeyError) as exc:
        await _mark_validation_failed(session_factory, tenant, batch_id, str(exc))
        raise PermanentJobError("Import validation failed.") from exc
    finally:
        if staged is not None:
            staged.close()


async def _file_chunks(handle: BinaryIO) -> AsyncIterator[bytes]:
    while chunk := await asyncio.to_thread(handle.read, 64 * 1024):
        yield chunk


async def generate_error_report(
    tenant: TenantContext,
    *,
    batch_id: UUID,
    control: JobControl,
    storage: StorageProvider,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await control.checkpoint()
    async with tenant_session(session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        existing_key = batch.error_report_key
        if batch.status not in {
            ImportStatus.VALIDATED,
            ImportStatus.QUEUED,
            ImportStatus.PROCESSING,
            ImportStatus.COMPLETED,
            ImportStatus.COMPLETED_WITH_ERRORS,
        }:
            raise PermanentJobError("Import issues are not ready for reporting.")
    if existing_key is not None and await storage.head(existing_key) is not None:
        return

    writer = ErrorReportWriter()
    cursor: str | None = None
    while True:
        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            rows, cursor = await ImportsRepository(session, tenant).list_issue_rows(
                batch_id, cursor=cursor, limit=500
            )
        writer.write_rows(rows)
        if cursor is None:
            break
    handle = writer.finish()
    key = import_error_key(tenant.organization_id, batch_id)
    try:
        await storage.upload(key, _file_chunks(handle), content_type="text/csv")
    finally:
        handle.close()

    async with tenant_session(session_factory, tenant) as session:
        batch = await ImportsRepository(session, tenant).get_batch(batch_id, for_update=True)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        batch.error_report_key = key
