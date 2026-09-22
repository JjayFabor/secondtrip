"""Import state transitions and storage orchestration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import EntitlementExceededError, NotFoundError
from app.core.ids import new_id
from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.modules.billing.entitlements.keys import EntitlementKey
from app.modules.billing.entitlements.service import EntitlementService
from app.modules.imports.errors import (
    DuplicateImportError,
    ImportStateConflictError,
    InvalidMappingError,
    InvalidUploadError,
)
from app.modules.imports.mapping.document import FieldMapping, MappingDocument
from app.modules.imports.mapping.suggester import mapping_signature, suggest_mappings
from app.modules.imports.models import ImportBatch, ImportStatus
from app.modules.imports.profiling import ColumnProfile, InferredType
from app.modules.imports.repository import ImportsRepository
from app.modules.imports.schemas import DetectedColumnOut, ImportPreviewOut
from app.modules.jobs.service import resolve_csv_source_system
from app.modules.tasks.service import PostgresJobQueue
from app.providers.storage.base import StorageProvider
from app.providers.storage.keys import import_source_key
from app.providers.storage.types import ObjectMetadata, PresignedUpload


@dataclass(frozen=True, slots=True)
class ImportCreation:
    batch: ImportBatch
    upload: PresignedUpload


async def create_import(
    session: AsyncSession,
    repository: ImportsRepository,
    entitlements: EntitlementService,
    storage: StorageProvider,
    settings: Settings,
    tenant: TenantContext,
    *,
    original_filename: str,
    source_system_id: UUID | None,
) -> ImportCreation:
    monthly = await entitlements.reserve(tenant, EntitlementKey.IMPORTS_PER_MONTH)
    if not monthly.allowed:
        raise EntitlementExceededError(monthly.reason or "Monthly import limit reached.")

    resolved_source_system_id = await resolve_csv_source_system(
        session,
        organization_id=tenant.organization_id,
        source_system_id=source_system_id,
    )
    if resolved_source_system_id is None:
        raise NotFoundError("Source system not found.")
    batch_id = new_id()
    key = import_source_key(tenant.organization_id, batch_id)
    batch = await repository.create_batch(
        batch_id=batch_id,
        source_system_id=resolved_source_system_id,
        created_by_user_id=tenant.actor_user_id,
        original_filename=original_filename,
        storage_key=key,
    )
    plan_file_limit = await entitlements.limit(tenant, EntitlementKey.IMPORT_FILE_BYTES)
    upload_limit = settings.import_max_file_bytes
    if plan_file_limit is not None:
        upload_limit = min(upload_limit, plan_file_limit)
    upload = await storage.signed_upload_url(
        key,
        content_type="text/csv",
        max_bytes=upload_limit,
        expires_in=settings.storage_upload_url_ttl_seconds,
    )
    return ImportCreation(batch=batch, upload=upload)


async def verify_uploaded_object(
    storage: StorageProvider,
    key: str,
    *,
    max_bytes: int,
) -> tuple[ObjectMetadata, bytes]:
    metadata = await storage.head(key)
    if metadata is None:
        raise InvalidUploadError("The uploaded object was not found; request a new upload URL.")
    if metadata.size_bytes > max_bytes:
        await storage.delete(key)
        raise EntitlementExceededError(
            f"The uploaded file is {metadata.size_bytes} bytes; the current limit is {max_bytes}."
        )
    digest = hashlib.sha256()
    streamed_bytes = 0
    async for chunk in storage.download(key):
        streamed_bytes += len(chunk)
        if streamed_bytes > max_bytes:
            await storage.delete(key)
            raise EntitlementExceededError("The uploaded file exceeds the current file-size limit.")
        digest.update(chunk)
    if streamed_bytes != metadata.size_bytes:
        raise InvalidUploadError("The uploaded object changed while it was being verified.")
    return metadata, digest.digest()


async def confirm_upload(
    session: AsyncSession,
    repository: ImportsRepository,
    queue: PostgresJobQueue,
    tenant: TenantContext,
    *,
    batch_id: UUID,
    metadata: ObjectMetadata,
    digest: bytes,
    allow_duplicate: bool,
) -> ImportBatch:
    batch = await repository.get_batch(batch_id, for_update=True)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status is not ImportStatus.AWAITING_FILE:
        if batch.file_sha256 == digest and batch.status in {
            ImportStatus.UPLOADED,
            ImportStatus.PROFILING,
            ImportStatus.AWAITING_MAPPING,
        }:
            return batch
        raise ImportStateConflictError(f"Import cannot accept an upload while {batch.status}.")

    duplicate = await repository.find_original_by_hash(digest, excluding_batch_id=batch.id)
    if duplicate is not None and not allow_duplicate:
        raise DuplicateImportError(
            f"These bytes were already uploaded in import {duplicate.id} on "
            f"{duplicate.created_at.date().isoformat()}."
        )

    batch.file_size_bytes = metadata.size_bytes
    batch.file_sha256 = digest
    batch.duplicate_of_batch_id = duplicate.id if duplicate is not None else None
    batch.status = ImportStatus.UPLOADED
    batch.failure_reason = None
    await queue.enqueue(
        session,
        organization_id=tenant.organization_id,
        job_type="import.profile",
        payload={"batch_id": str(batch.id), "version": 1},
        idempotency_key=f"import.profile:{batch.id}",
        enqueued_by_user_id=tenant.actor_user_id,
        correlation_id=tenant.request_id,
    )
    await session.flush()
    return batch


def _columns_from_batch(batch: ImportBatch) -> tuple[ColumnProfile, ...]:
    if batch.detected_columns is None:
        raise ImportStateConflictError("Import profiling has not produced columns yet.")
    try:
        validated = [DetectedColumnOut.model_validate(item) for item in batch.detected_columns]
        return tuple(
            ColumnProfile(
                name=item.name,
                ordinal=item.index,
                sample_values=tuple(item.sample_values),
                inferred_type=InferredType(item.inferred_type),
            )
            for item in validated
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ImportStateConflictError("Stored import profile is invalid.") from exc


async def build_preview(repository: ImportsRepository, *, batch_id: UUID) -> ImportPreviewOut:
    batch = await repository.get_batch(batch_id)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status in {ImportStatus.AWAITING_FILE, ImportStatus.UPLOADED, ImportStatus.PROFILING}:
        raise ImportStateConflictError("Import profiling is not complete yet.")
    if batch.encoding is None or batch.delimiter is None or batch.has_header is None:
        raise ImportStateConflictError("Import profile is incomplete.")

    columns = _columns_from_batch(batch)
    signature = mapping_signature(tuple(column.name for column in columns))
    template = await repository.find_template_by_signature(
        signature, source_system_id=batch.source_system_id
    )
    available = {column.name for column in columns}
    suggested_mapping: MappingDocument | None = None
    matched_template_id: UUID | None = None
    if template is not None:
        try:
            candidate = MappingDocument.model_validate(template.mapping)
            candidate.validate_source_columns(available)
            suggested_mapping = candidate
            matched_template_id = template.id
        except (ValueError, TypeError):
            template = None

    suggestions = suggest_mappings(columns)
    if suggested_mapping is None:
        fields = {
            suggestion.target_field: FieldMapping(source_column=suggestion.source_column)
            for suggestion in suggestions
        }
        if "service_date" in fields and ({"customer_name", "customer_external_id"} & fields.keys()):
            suggested_mapping = MappingDocument(version=1, fields=fields)

    return ImportPreviewOut.model_validate(
        {
            "batch_id": batch.id,
            "encoding": batch.encoding,
            "delimiter": batch.delimiter,
            "has_header": batch.has_header,
            "approximate_row_count": batch.total_rows,
            "columns": batch.detected_columns,
            "sample_rows": batch.sample_rows or [],
            "profile_issues": batch.profile_issues,
            "suggested_mapping": suggested_mapping,
            "suggestions": suggestions,
            "matched_template_id": matched_template_id,
        }
    )


async def apply_mapping(
    session: AsyncSession,
    repository: ImportsRepository,
    *,
    batch_id: UUID,
    mapping: MappingDocument,
    template_id: UUID | None,
) -> ImportBatch:
    batch = await repository.get_batch(batch_id, for_update=True)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status is not ImportStatus.AWAITING_MAPPING:
        raise ImportStateConflictError(f"Import cannot be mapped while {batch.status}.")
    columns = _columns_from_batch(batch)
    try:
        mapping.validate_source_columns({column.name for column in columns})
    except ValueError as exc:
        raise InvalidMappingError(str(exc)) from exc
    template = None
    if template_id is not None:
        template = await repository.get_template(template_id)
        if template is None:
            raise NotFoundError("Import template not found.")
    batch.mapping = mapping.model_dump(mode="json")
    batch.template_id = template_id
    if template is not None:
        template.usage_count += 1
        template.last_used_at = datetime.now(UTC)
    await session.flush()
    return batch


async def request_validation(
    session: AsyncSession,
    repository: ImportsRepository,
    queue: PostgresJobQueue,
    tenant: TenantContext,
    *,
    batch_id: UUID,
) -> ImportBatch:
    batch = await repository.get_batch(batch_id, for_update=True)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status in {ImportStatus.VALIDATING, ImportStatus.VALIDATED}:
        return batch
    if batch.status is not ImportStatus.AWAITING_MAPPING or batch.mapping is None:
        raise ImportStateConflictError(f"Import cannot be validated while {batch.status}.")
    if batch.storage_key is None or batch.encoding is None or batch.delimiter is None:
        raise ImportStateConflictError("Import profile is incomplete.")

    batch.status = ImportStatus.VALIDATING
    batch.started_at = datetime.now(UTC)
    batch.processed_rows = 0
    batch.warning_rows = 0
    batch.error_rows = 0
    batch.skipped_rows = 0
    batch.error_report_key = None
    batch.failure_reason = None
    await queue.enqueue(
        session,
        organization_id=tenant.organization_id,
        job_type="import.validate",
        payload={"batch_id": str(batch.id), "version": 1},
        priority=10,
        idempotency_key=f"import.validate:{batch.id}",
        enqueued_by_user_id=tenant.actor_user_id,
        correlation_id=tenant.request_id,
    )
    await session.flush()
    return batch


async def request_commit(
    session: AsyncSession,
    repository: ImportsRepository,
    entitlements: EntitlementService,
    queue: PostgresJobQueue,
    tenant: TenantContext,
    *,
    batch_id: UUID,
) -> ImportBatch:
    """Reserve actual-row capacity and enqueue processing in one transaction."""
    batch = await repository.get_batch(batch_id, for_update=True)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status is not ImportStatus.VALIDATED:
        raise ImportStateConflictError(f"Import cannot be committed while {batch.status}.")

    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{tenant.organization_id}:active-imports"},
    )
    concurrent_limit = await entitlements.limit(tenant, EntitlementKey.CONCURRENT_IMPORTS)
    active = await repository.count_active_batches()
    if concurrent_limit is not None and active >= concurrent_limit:
        raise EntitlementExceededError(
            f"Concurrent import usage is {active} of {concurrent_limit}."
        )

    importable_rows = batch.total_rows - batch.error_rows - batch.skipped_rows
    if importable_rows > 0:
        jobs = await entitlements.reserve(
            tenant, EntitlementKey.JOBS_IMPORTED, amount=importable_rows
        )
        if not jobs.allowed:
            raise EntitlementExceededError(jobs.reason or "Imported job limit reached.")

    batch.status = ImportStatus.QUEUED
    batch.processed_rows = 0
    batch.created_jobs = 0
    batch.updated_jobs = 0
    batch.cancel_requested_at = None
    batch.completed_at = None
    batch.failure_reason = None
    await queue.enqueue(
        session,
        organization_id=tenant.organization_id,
        job_type="import.process",
        payload={"batch_id": str(batch.id), "version": 1},
        priority=10,
        idempotency_key=f"import.process:{batch.id}",
        enqueued_by_user_id=tenant.actor_user_id,
        correlation_id=tenant.request_id,
    )
    await session.flush()
    return batch


async def request_cancellation(
    session: AsyncSession,
    repository: ImportsRepository,
    queue: PostgresJobQueue,
    tenant: TenantContext,
    *,
    batch_id: UUID,
) -> ImportBatch:
    batch = await repository.get_batch(batch_id, for_update=True)
    if batch is None:
        raise NotFoundError("Import not found.")
    if batch.status is ImportStatus.CANCELLED:
        return batch
    if batch.status not in {
        ImportStatus.PROFILING,
        ImportStatus.VALIDATING,
        ImportStatus.QUEUED,
        ImportStatus.PROCESSING,
    }:
        raise ImportStateConflictError(f"Import cannot be cancelled while {batch.status}.")
    now = datetime.now(UTC)
    batch.cancel_requested_at = now
    batch.completed_at = now
    batch.status = ImportStatus.CANCELLED
    await queue.request_cancel(
        session,
        organization_id=tenant.organization_id,
        idempotency_keys=(
            f"import.profile:{batch.id}",
            f"import.validate:{batch.id}",
            f"import.error_report:{batch.id}",
            f"import.process:{batch.id}",
        ),
    )
    await session.flush()
    return batch
