"""Public operational-job write boundary used by ingestion adapters."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from sqlalchemy import func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.jobs.models import (
    Job,
    JobNote,
    ServiceCategory,
    SourceSystem,
    SourceSystemKind,
)
from app.modules.jobs.schemas import JobStatus


@dataclass(frozen=True, slots=True)
class JobWrite:
    source_system_id: UUID
    external_id: str | None
    natural_key_hash: bytes
    import_batch_id: UUID
    customer_id: UUID
    location_id: UUID | None
    equipment_id: UUID | None
    technician_id: UUID | None
    service_category_id: UUID | None
    raw_service_category: str | None
    raw_job_type: str | None
    status: JobStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    service_date: date
    duration_minutes: int | None
    summary: str | None
    description: str | None
    symptoms_text: str | None
    diagnosis_text: str | None
    resolution_text: str | None
    invoice_number: str | None
    revenue_amount: Decimal | None
    parts_amount: Decimal | None
    labor_amount: Decimal | None
    currency_code: str
    is_warranty: bool
    warranty_reference: str | None
    extra_fields: dict[str, object]


@dataclass(frozen=True, slots=True)
class JobWriteResult:
    job_id: UUID
    created: bool
    natural_key_collision: bool


@dataclass(frozen=True, slots=True)
class ServiceCategoryWrite:
    key: str
    label: str


async def resolve_csv_source_system(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_system_id: UUID | None,
) -> UUID | None:
    """Resolve or create the tenant's default CSV source without leaking the ORM model."""
    if source_system_id is not None:
        return cast(
            UUID | None,
            await session.scalar(
                select(SourceSystem.id).where(
                    SourceSystem.organization_id == organization_id,
                    SourceSystem.id == source_system_id,
                )
            )
        )
    existing = await session.scalar(
        select(SourceSystem)
        .where(
            SourceSystem.organization_id == organization_id,
            SourceSystem.kind == SourceSystemKind.CSV_UPLOAD,
            or_(SourceSystem.is_default.is_(True), SourceSystem.name == "CSV uploads"),
        )
        .order_by(SourceSystem.is_default.desc(), SourceSystem.created_at)
        .limit(1)
    )
    if existing is not None:
        existing.is_default = True
        return existing.id
    source = SourceSystem(
        organization_id=organization_id,
        kind=SourceSystemKind.CSV_UPLOAD,
        name="CSV uploads",
        is_default=True,
    )
    session.add(source)
    await session.flush()
    return source.id


async def get_import_service_date_range(
    session: AsyncSession,
    *,
    organization_id: UUID,
    import_batch_id: UUID,
) -> tuple[date, date] | None:
    """Return the job-date range touched by an import for downstream detection."""
    first_date, last_date = (
        await session.execute(
            select(func.min(Job.service_date), func.max(Job.service_date)).where(
                Job.organization_id == organization_id,
                Job.last_import_batch_id == import_batch_id,
                Job.deleted_at.is_(None),
            )
        )
    ).one()
    if first_date is None or last_date is None:
        return None
    return cast(date, first_date), cast(date, last_date)


async def bulk_resolve_service_categories(
    session: AsyncSession,
    *,
    organization_id: UUID,
    writes: list[ServiceCategoryWrite],
) -> dict[str, UUID]:
    keyed = {item.key: item.label for item in writes}
    if not keyed:
        return {}
    lock_keys = sorted(f"{organization_id}:service-category:{key}" for key in keyed)
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(lock_key, 0)) "
            "FROM unnest(CAST(:lock_keys AS text[])) AS lock_key ORDER BY lock_key"
        ),
        {"lock_keys": lock_keys},
    )
    values = [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "key": key,
            "label": label,
        }
        for key, label in keyed.items()
    ]
    statement = insert(ServiceCategory)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[ServiceCategory.organization_id, ServiceCategory.key],
            set_={"label": statement.excluded.label},
        ),
        values,
    )
    rows = (
        await session.execute(
            select(ServiceCategory.id, ServiceCategory.key).where(
                ServiceCategory.organization_id == organization_id,
                ServiceCategory.key.in_(list(keyed)),
            )
        )
    ).all()
    return {key: identifier for identifier, key in rows}


async def bulk_upsert_jobs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    writes: list[JobWrite],
) -> dict[bytes, JobWriteResult]:
    if not writes:
        return {}
    external = {
        (item.source_system_id, item.external_id): item
        for item in writes
        if item.external_id is not None
    }
    natural = {item.natural_key_hash: item for item in writes if item.external_id is None}
    lock_keys = sorted(
        f"{organization_id}:job:{item.source_system_id}:"
        f"{item.external_id or item.natural_key_hash.hex()}"
        for item in [*external.values(), *natural.values()]
    )
    await session.execute(
        text(
            "SELECT pg_advisory_xact_lock(hashtextextended(lock_key, 0)) "
            "FROM unnest(CAST(:lock_keys AS text[])) AS lock_key ORDER BY lock_key"
        ),
        {"lock_keys": lock_keys},
    )
    existing_external: dict[tuple[UUID, str], UUID] = {}
    if external:
        existing_external = {
            (source_system_id, external_id): identifier
            for identifier, source_system_id, external_id in (
                await session.execute(
                    select(Job.id, Job.source_system_id, Job.external_id).where(
                        Job.organization_id == organization_id,
                        tuple_(Job.source_system_id, Job.external_id).in_(list(external)),
                        Job.deleted_at.is_(None),
                    )
                )
            ).all()
            if external_id is not None
        }
    existing_natural: dict[bytes, UUID] = {}
    if natural:
        existing_natural = {
            digest: identifier
            for identifier, digest in (
                await session.execute(
                    select(Job.id, Job.natural_key_hash).where(
                        Job.organization_id == organization_id,
                        Job.natural_key_hash.in_(list(natural)),
                        Job.deleted_at.is_(None),
                    )
                )
            ).all()
        }

    async def execute_group(
        group: list[JobWrite], *, uses_external_id: bool, update_existing: bool
    ) -> dict[bytes, UUID]:
        if not group:
            return {}
        identifiers = {item.natural_key_hash: new_id() for item in group}
        values = [
            {
                "id": identifiers[item.natural_key_hash],
                "organization_id": organization_id,
                "source_system_id": item.source_system_id,
                "external_id": item.external_id,
                "natural_key_hash": item.natural_key_hash,
                "first_import_batch_id": item.import_batch_id,
                "last_import_batch_id": item.import_batch_id,
                "customer_id": item.customer_id,
                "location_id": item.location_id,
                "equipment_id": item.equipment_id,
                "technician_id": item.technician_id,
                "service_category_id": item.service_category_id,
                "raw_service_category": item.raw_service_category,
                "raw_job_type": item.raw_job_type,
                "status": item.status,
                "scheduled_at": item.scheduled_at,
                "started_at": item.started_at,
                "completed_at": item.completed_at,
                "service_date": item.service_date,
                "duration_minutes": item.duration_minutes,
                "summary": item.summary,
                "description": item.description,
                "symptoms_text": item.symptoms_text,
                "diagnosis_text": item.diagnosis_text,
                "resolution_text": item.resolution_text,
                "invoice_number": item.invoice_number,
                "revenue_amount": item.revenue_amount,
                "parts_amount": item.parts_amount,
                "labor_amount": item.labor_amount,
                "currency_code": item.currency_code,
                "is_warranty": item.is_warranty,
                "is_no_charge": item.revenue_amount == Decimal("0"),
                "warranty_reference": item.warranty_reference,
                "extra_fields": item.extra_fields,
            }
            for item in group
        ]
        statement = insert(Job)
        if not update_existing:
            await session.execute(statement, values)
            return identifiers
        excluded = statement.excluded
        update_values = {
            "natural_key_hash": excluded.natural_key_hash,
            "last_import_batch_id": excluded.last_import_batch_id,
            "customer_id": excluded.customer_id,
            "location_id": excluded.location_id,
            "equipment_id": excluded.equipment_id,
            "technician_id": excluded.technician_id,
            "service_category_id": excluded.service_category_id,
            "raw_service_category": excluded.raw_service_category,
            "raw_job_type": excluded.raw_job_type,
            "status": excluded.status,
            "scheduled_at": excluded.scheduled_at,
            "started_at": excluded.started_at,
            "completed_at": excluded.completed_at,
            "service_date": excluded.service_date,
            "duration_minutes": excluded.duration_minutes,
            "summary": excluded.summary,
            "description": excluded.description,
            "symptoms_text": excluded.symptoms_text,
            "diagnosis_text": excluded.diagnosis_text,
            "resolution_text": excluded.resolution_text,
            "invoice_number": excluded.invoice_number,
            "revenue_amount": excluded.revenue_amount,
            "parts_amount": excluded.parts_amount,
            "labor_amount": excluded.labor_amount,
            "currency_code": excluded.currency_code,
            "is_warranty": excluded.is_warranty,
            "is_no_charge": excluded.is_no_charge,
            "warranty_reference": excluded.warranty_reference,
            "extra_fields": excluded.extra_fields,
            "updated_at": func.now(),
        }
        if uses_external_id:
            statement = statement.on_conflict_do_update(
                index_elements=[
                    Job.organization_id,
                    Job.source_system_id,
                    Job.external_id,
                ],
                index_where=Job.external_id.is_not(None) & Job.deleted_at.is_(None),
                set_=update_values,
            )
        else:
            statement = statement.on_conflict_do_update(
                index_elements=[Job.organization_id, Job.natural_key_hash],
                index_where=Job.deleted_at.is_(None),
                set_=update_values,
            )
        await session.execute(statement, values)
        return {}

    created_ids = await execute_group(
        [item for key, item in external.items() if key not in existing_external],
        uses_external_id=True,
        update_existing=False,
    )
    await execute_group(
        [item for key, item in external.items() if key in existing_external],
        uses_external_id=True,
        update_existing=True,
    )
    created_ids.update(
        await execute_group(
            [item for key, item in natural.items() if key not in existing_natural],
            uses_external_id=False,
            update_existing=False,
        )
    )
    await execute_group(
        [item for key, item in natural.items() if key in existing_natural],
        uses_external_id=False,
        update_existing=True,
    )
    results: dict[bytes, JobWriteResult] = {}
    for key, item in external.items():
        identifier = existing_external.get(key)
        created = identifier is None
        if identifier is None:
            identifier = created_ids[item.natural_key_hash]
        results[item.natural_key_hash] = JobWriteResult(
            job_id=identifier,
            created=created,
            natural_key_collision=False,
        )
    for digest in natural:
        identifier = existing_natural.get(digest)
        created = identifier is None
        if identifier is None:
            identifier = created_ids[digest]
        results[digest] = JobWriteResult(
            job_id=identifier,
            created=created,
            natural_key_collision=not created,
        )
    return results


async def bulk_add_job_notes(
    session: AsyncSession,
    *,
    organization_id: UUID,
    notes: list[tuple[UUID, str, str | None, datetime | None]],
) -> None:
    values = []
    for job_id, body, author_name, occurred_at in notes:
        values.append(
            {
                "id": new_id(),
                "organization_id": organization_id,
                "job_id": job_id,
                "body": body,
                "author_name": author_name,
                "occurred_at": occurred_at or datetime.now(UTC),
                "content_hash": hashlib.sha256(body.encode()).digest(),
            }
        )
    if not values:
        return
    statement = insert(JobNote)
    await session.execute(
        statement.on_conflict_do_nothing(
            index_elements=[
                JobNote.organization_id,
                JobNote.job_id,
                JobNote.content_hash,
            ]
        ),
        values,
    )


async def resolve_service_category(
    session: AsyncSession,
    *,
    organization_id: UUID,
    key: str,
    label: str,
) -> UUID:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{organization_id}:service-category:{key}"},
    )
    category = (
        await session.execute(
            select(ServiceCategory).where(
                ServiceCategory.organization_id == organization_id,
                ServiceCategory.key == key,
            )
        )
    ).scalar_one_or_none()
    if category is None:
        category = ServiceCategory(organization_id=organization_id, key=key, label=label)
        session.add(category)
        await session.flush()
    return category.id


async def upsert_job(
    session: AsyncSession,
    *,
    organization_id: UUID,
    values: JobWrite,
) -> JobWriteResult:
    identity = values.external_id or values.natural_key_hash.hex()
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{organization_id}:job:{values.source_system_id}:{identity}"},
    )
    statement = select(Job).where(
        Job.organization_id == organization_id,
        Job.deleted_at.is_(None),
    )
    if values.external_id is not None:
        statement = statement.where(
            Job.source_system_id == values.source_system_id,
            Job.external_id == values.external_id,
        )
    else:
        statement = statement.where(Job.natural_key_hash == values.natural_key_hash)
    job = (await session.execute(statement)).scalar_one_or_none()
    created = job is None
    collision = job is not None and values.external_id is None
    if job is None:
        job = Job(
            organization_id=organization_id,
            source_system_id=values.source_system_id,
            external_id=values.external_id,
            natural_key_hash=values.natural_key_hash,
            first_import_batch_id=values.import_batch_id,
            currency_code=values.currency_code,
            service_date=values.service_date,
        )
        session.add(job)

    # Mapped job fields are authoritative on every re-import.
    job.natural_key_hash = values.natural_key_hash
    job.last_import_batch_id = values.import_batch_id
    job.customer_id = values.customer_id
    job.location_id = values.location_id
    job.equipment_id = values.equipment_id
    job.technician_id = values.technician_id
    job.service_category_id = values.service_category_id
    job.raw_service_category = values.raw_service_category
    job.raw_job_type = values.raw_job_type
    job.status = values.status
    job.scheduled_at = values.scheduled_at
    job.started_at = values.started_at
    job.completed_at = values.completed_at
    job.service_date = values.service_date
    job.duration_minutes = values.duration_minutes
    job.summary = values.summary
    job.description = values.description
    job.symptoms_text = values.symptoms_text
    job.diagnosis_text = values.diagnosis_text
    job.resolution_text = values.resolution_text
    job.invoice_number = values.invoice_number
    job.revenue_amount = values.revenue_amount
    job.parts_amount = values.parts_amount
    job.labor_amount = values.labor_amount
    job.currency_code = values.currency_code
    job.is_warranty = values.is_warranty
    job.is_no_charge = values.revenue_amount == Decimal("0")
    job.warranty_reference = values.warranty_reference
    job.extra_fields = values.extra_fields
    await session.flush()
    return JobWriteResult(job.id, created, collision)


async def add_job_note(
    session: AsyncSession,
    *,
    organization_id: UUID,
    job_id: UUID,
    body: str | None,
    author_name: str | None,
    occurred_at: datetime | None,
) -> None:
    if body is None:
        return
    digest = hashlib.sha256(body.encode()).digest()
    existing = await session.scalar(
        select(JobNote.id).where(
            JobNote.organization_id == organization_id,
            JobNote.job_id == job_id,
            JobNote.content_hash == digest,
        )
    )
    if existing is None:
        session.add(
            JobNote(
                organization_id=organization_id,
                job_id=job_id,
                body=body,
                author_name=author_name,
                occurred_at=occurred_at or datetime.now(UTC),
                content_hash=digest,
            )
        )
