"""Checkpointed conversion of validated import rows into operational data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.audit.schemas import ActorType
from app.modules.audit.service import record as record_audit
from app.modules.customers.service import (
    register_customer_job,
    resolve_customer,
    resolve_equipment,
    resolve_location,
)
from app.modules.detection.schemas import DetectionTrigger
from app.modules.detection.service import enqueue_detection_run
from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.models import ImportRowStatus, ImportStatus
from app.modules.imports.normalization.dates import infer_date_order
from app.modules.imports.normalization.identity import (
    customer_key,
    equipment_key,
    external_job_key,
    job_key,
    location_key,
    technician_key,
)
from app.modules.imports.normalization.records import SourceRecord, deserialize_source_record
from app.modules.imports.normalization.text import normalize_name
from app.modules.imports.processing.reader import ParsedCsvRow
from app.modules.imports.processing.validator import serialize_issues, validate_row
from app.modules.imports.processing.writer import ValidatedWrite, write_validated_chunk
from app.modules.imports.repository import ImportsRepository
from app.modules.jobs.schemas import JobStatus
from app.modules.jobs.service import (
    JobWrite,
    add_job_note,
    get_import_service_date_range,
    resolve_service_category,
    upsert_job,
)
from app.modules.organizations.service import get_organization_import_settings
from app.modules.tasks.control import JobControl
from app.modules.tasks.errors import JobCancelled, PermanentJobError
from app.modules.tasks.service import PostgresJobQueue
from app.modules.workforce.service import resolve_technician


def _label(value: str | None, *fallbacks: str | None) -> str:
    for candidate in (value, *fallbacks):
        if candidate:
            return candidate
    raise ValueError("Validated identity has no display value.")


async def _process_record(
    session: AsyncSession,
    tenant: TenantContext,
    *,
    batch_id: UUID,
    source_system_id: UUID,
    currency_code: str,
    record: SourceRecord,
) -> tuple[UUID, bool, bool]:
    customer_identity = customer_key(
        tenant.organization_id,
        source_system_id,
        external_id=record.customer_external_id,
        phone_e164=record.customer_phone_e164,
        name=record.customer_name,
        postal_code=record.postal_code,
    )
    if customer_identity is None:
        raise ValueError("Validated row has no customer identity.")
    display_name = _label(
        record.customer_name,
        record.customer_external_id,
        record.customer_phone_raw,
        record.customer_phone_e164,
    )
    customer = await resolve_customer(
        session,
        organization_id=tenant.organization_id,
        source_system_id=source_system_id,
        natural_key_hash=customer_identity.digest,
        external_id=record.customer_external_id,
        display_name=display_name,
        normalized_name=normalize_name(display_name) or display_name.casefold(),
        email=record.customer_email,
        phone_raw=record.customer_phone_raw,
        phone_e164=record.customer_phone_e164,
    )

    location_identity = location_key(
        tenant.organization_id,
        source_system_id,
        external_id=record.location_external_id,
        customer_digest=customer.natural_key_hash,
        address_line1=record.address_line1,
        postal_code=record.postal_code,
    )
    location_id: UUID | None = None
    if location_identity is not None:
        location = await resolve_location(
            session,
            organization_id=tenant.organization_id,
            customer_id=customer.id,
            address_hash=location_identity.digest,
            external_id=record.location_external_id,
            address_line1=record.address_line1,
            city=record.city,
            region=record.region,
            postal_code=record.postal_code,
        )
        location_id = location.id

    equipment_identity = equipment_key(
        tenant.organization_id,
        source_system_id,
        external_id=record.equipment_external_id,
        serial_number=record.equipment_serial,
        location_digest=location_identity.digest if location_identity else None,
        manufacturer=record.equipment_manufacturer,
        model=record.equipment_model,
        equipment_type=record.equipment_type,
    )
    equipment_id: UUID | None = None
    if equipment_identity is not None:
        equipment = await resolve_equipment(
            session,
            organization_id=tenant.organization_id,
            customer_id=customer.id,
            location_id=location_id,
            natural_key_hash=equipment_identity.digest,
            external_id=record.equipment_external_id,
            serial_number=record.equipment_serial,
            manufacturer=record.equipment_manufacturer,
            model=record.equipment_model,
            equipment_type=record.equipment_type,
        )
        equipment_id = equipment.id

    technician_identity = technician_key(
        tenant.organization_id,
        source_system_id,
        external_id=record.technician_external_id,
        employee_code=record.technician_code,
        name=record.technician_name,
    )
    technician_id: UUID | None = None
    if technician_identity is not None:
        technician_name = _label(
            record.technician_name,
            record.technician_code,
            record.technician_external_id,
        )
        technician_id = await resolve_technician(
            session,
            organization_id=tenant.organization_id,
            natural_key_hash=technician_identity.digest,
            external_id=record.technician_external_id,
            full_name=technician_name,
            normalized_name=normalize_name(technician_name) or technician_name.casefold(),
            employee_code=record.technician_code,
        )

    category_id: UUID | None = None
    if record.service_category:
        category_key = (normalize_name(record.service_category) or record.service_category).replace(
            " ", "-"
        )
        category_id = await resolve_service_category(
            session,
            organization_id=tenant.organization_id,
            key=category_key,
            label=record.service_category,
        )

    natural_identity = (
        external_job_key(tenant.organization_id, source_system_id, record.external_job_id)
        if record.external_job_id
        else job_key(
            tenant.organization_id,
            customer.natural_key_hash,
            service_date=record.service_date,
            summary=record.summary,
            description=record.description,
            invoice_number=record.invoice_number,
        )
    )
    result = await upsert_job(
        session,
        organization_id=tenant.organization_id,
        values=JobWrite(
            source_system_id=source_system_id,
            external_id=record.external_job_id,
            natural_key_hash=natural_identity.digest,
            import_batch_id=batch_id,
            customer_id=customer.id,
            location_id=location_id,
            equipment_id=equipment_id,
            technician_id=technician_id,
            service_category_id=category_id,
            raw_service_category=record.service_category,
            raw_job_type=record.job_type,
            status=JobStatus(record.job_status or JobStatus.UNKNOWN.value),
            scheduled_at=record.scheduled_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
            service_date=record.service_date,
            duration_minutes=record.duration_minutes,
            summary=record.summary,
            description=record.description,
            symptoms_text=record.symptoms,
            diagnosis_text=record.diagnosis,
            resolution_text=record.resolution,
            invoice_number=record.invoice_number,
            revenue_amount=record.revenue_amount,
            parts_amount=record.parts_amount,
            labor_amount=record.labor_amount,
            currency_code=currency_code,
            is_warranty=record.is_warranty,
            warranty_reference=record.warranty_reference,
            extra_fields=dict(record.extra_fields),
        ),
    )
    await add_job_note(
        session,
        organization_id=tenant.organization_id,
        job_id=result.job_id,
        body=record.technician_notes,
        author_name=record.technician_name,
        occurred_at=record.completed_at,
    )
    await register_customer_job(
        session,
        organization_id=tenant.organization_id,
        customer_id=customer.id,
        service_date=record.service_date,
        created=result.created,
    )
    return result.job_id, result.created, result.natural_key_collision


def _possible_duplicate() -> dict[str, object]:
    serialized = serialize_issues(
        (
            ImportIssue(
                code=IssueCode.POSSIBLE_DUPLICATE,
                severity=IssueSeverity.WARNING,
                message=(
                    "The natural job key matched an existing job; the existing job was updated."
                ),
            ),
        )
    )[0]
    return cast(dict[str, object], serialized)


async def process_import(
    tenant: TenantContext,
    *,
    batch_id: UUID,
    control: JobControl,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    queue: PostgresJobQueue,
) -> None:
    await control.checkpoint()
    async with tenant_session(session_factory, tenant) as session:
        repository = ImportsRepository(session, tenant)
        batch = await repository.get_batch(batch_id, for_update=True)
        if batch is None:
            raise PermanentJobError("Import batch no longer exists.")
        if batch.status in {ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS}:
            return
        if batch.status is ImportStatus.CANCELLED:
            raise JobCancelled
        if batch.status not in {ImportStatus.QUEUED, ImportStatus.PROCESSING}:
            raise PermanentJobError("Import batch is not ready for processing.")
        if batch.mapping is None or batch.has_header is None:
            raise PermanentJobError("Import mapping is incomplete.")
        mapping = MappingDocument.model_validate(batch.mapping)
        source_system_id = batch.source_system_id
        first_row_number = 2 if batch.has_header else 1
        service_date_column = mapping.fields["service_date"].source_column
        samples = await repository.sample_source_values(batch_id, source_column=service_date_column)
        date_order = infer_date_order(samples)
        organization = await get_organization_import_settings(session, tenant.organization_id)
        batch.status = ImportStatus.PROCESSING
        batch.started_at = batch.started_at or datetime.now(UTC)

    while True:
        await control.checkpoint()
        async with tenant_session(session_factory, tenant) as session:
            repository = ImportsRepository(session, tenant)
            batch = await repository.get_batch(batch_id, for_update=True)
            if batch is None:
                raise PermanentJobError("Import batch no longer exists.")
            if batch.status is ImportStatus.CANCELLED:
                raise JobCancelled
            if batch.status in {ImportStatus.COMPLETED, ImportStatus.COMPLETED_WITH_ERRORS}:
                return
            if batch.status is not ImportStatus.PROCESSING:
                raise PermanentJobError("Import batch changed state during processing.")
            rows = await repository.processing_rows(
                batch_id,
                first_row_number=first_row_number,
                processed_rows=batch.processed_rows,
                limit=settings.import_chunk_size,
            )
            if not rows:
                batch.status = (
                    ImportStatus.COMPLETED_WITH_ERRORS
                    if batch.error_rows
                    else ImportStatus.COMPLETED
                )
                batch.completed_at = datetime.now(UTC)
                await record_audit(
                    session,
                    organization_id=tenant.organization_id,
                    action="import.completed",
                    summary="Completed import processing",
                    actor_type=ActorType.SYSTEM,
                    actor_label="Import worker",
                    resource_type="import_batch",
                    resource_id=batch.id,
                    request_id=tenant.request_id,
                )
                date_range = await get_import_service_date_range(
                    session,
                    organization_id=tenant.organization_id,
                    import_batch_id=batch.id,
                )
                if date_range is not None:
                    await enqueue_detection_run(
                        session,
                        queue,
                        settings,
                        tenant,
                        trigger=DetectionTrigger.IMPORT_COMPLETED,
                        from_date=date_range[0],
                        to_date=date_range[1],
                        import_batch_id=batch.id,
                    )
                return

            legacy_raw_data = await repository.raw_data_for_rows(
                [row.id for row in rows if row.normalized_data is None]
            )

            writable: list[ValidatedWrite] = []
            writable_rows = {}
            row_updates: list[dict[str, object]] = []
            for row in rows:
                if row.status in {
                    ImportRowStatus.ERROR,
                    ImportRowStatus.SKIPPED_DUPLICATE,
                    ImportRowStatus.SKIPPED_FILTERED,
                    ImportRowStatus.IMPORTED,
                    ImportRowStatus.UPDATED,
                }:
                    continue
                record = (
                    deserialize_source_record(row.normalized_data)
                    if row.normalized_data is not None
                    else None
                )
                validation = None
                if record is None:
                    validation = validate_row(
                        ParsedCsvRow(
                            row_number=row.row_number,
                            raw_data={
                                key: str(value) for key, value in legacy_raw_data[row.id].items()
                            },
                            row_hash=row.row_hash,
                            issues=(),
                        ),
                        mapping,
                        organization_id=tenant.organization_id,
                        source_system_id=source_system_id,
                        organization_timezone=organization.timezone,
                        date_order=date_order,
                        max_field_bytes=settings.import_max_field_bytes,
                    )
                    record = validation.source_record
                if record is None:
                    assert validation is not None
                    if row.status is ImportRowStatus.WARNING:
                        batch.warning_rows -= 1
                    row_updates.append(
                        {
                            "id": str(row.id),
                            "status": ImportRowStatus.ERROR.value,
                            "issues": serialize_issues(validation.issues),
                            "job_id": None,
                        }
                    )
                    batch.error_rows += 1
                    continue
                writable.append(
                    ValidatedWrite(
                        row_number=row.row_number,
                        record=record,
                    )
                )
                writable_rows[row.row_number] = row

            results = await write_validated_chunk(
                session,
                organization_id=tenant.organization_id,
                source_system_id=source_system_id,
                batch_id=batch.id,
                currency_code=organization.currency_code,
                items=writable,
            )
            created_jobs = 0
            updated_jobs = 0
            for result in results:
                row = writable_rows[result.row_number]
                status = row.status
                issues = row.issues
                if result.natural_key_collision:
                    has_duplicate_issue = any(
                        issue.get("code") == IssueCode.POSSIBLE_DUPLICATE for issue in issues
                    )
                    if not has_duplicate_issue:
                        issues = [*issues, _possible_duplicate()]
                    if status is not ImportRowStatus.WARNING:
                        status = ImportRowStatus.WARNING
                        batch.warning_rows += 1
                elif status is not ImportRowStatus.WARNING:
                    status = ImportRowStatus.IMPORTED if result.created else ImportRowStatus.UPDATED
                row_updates.append(
                    {
                        "id": str(row.id),
                        "status": status.value,
                        "issues": issues,
                        "job_id": str(result.job_id),
                    }
                )
                if result.created:
                    created_jobs += 1
                else:
                    updated_jobs += 1
            await repository.update_processed_rows(row_updates)
            batch.created_jobs += created_jobs
            batch.updated_jobs += updated_jobs
            batch.processed_rows += len(rows)
