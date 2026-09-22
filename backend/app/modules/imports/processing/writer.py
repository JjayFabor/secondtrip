"""Bounded bulk writer for validated source-neutral import records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.service import (
    CustomerJobAggregate,
    CustomerWrite,
    EquipmentWrite,
    LocationWrite,
    bulk_register_customer_jobs,
    bulk_resolve_customers,
    bulk_resolve_equipment,
    bulk_resolve_locations,
)
from app.modules.imports.normalization.identity import (
    customer_key,
    equipment_key,
    external_job_key,
    job_key,
    location_key,
    technician_key,
)
from app.modules.imports.normalization.records import SourceRecord
from app.modules.imports.normalization.text import normalize_name
from app.modules.jobs.schemas import JobStatus
from app.modules.jobs.service import (
    JobWrite,
    ServiceCategoryWrite,
    bulk_add_job_notes,
    bulk_resolve_service_categories,
    bulk_upsert_jobs,
)
from app.modules.workforce.service import TechnicianWrite, bulk_resolve_technicians


@dataclass(frozen=True, slots=True)
class ValidatedWrite:
    row_number: int
    record: SourceRecord


@dataclass(frozen=True, slots=True)
class ChunkRowResult:
    row_number: int
    job_id: UUID
    created: bool
    natural_key_collision: bool


@dataclass(frozen=True, slots=True)
class _Identities:
    item: ValidatedWrite
    customer: bytes
    location: bytes | None
    equipment: bytes | None
    technician: bytes | None
    job: bytes
    category_key: str | None


def _label(value: str | None, *fallbacks: str | None) -> str:
    for candidate in (value, *fallbacks):
        if candidate:
            return candidate
    raise ValueError("Validated identity has no display value.")


async def write_validated_chunk(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_system_id: UUID,
    batch_id: UUID,
    currency_code: str,
    items: list[ValidatedWrite],
) -> list[ChunkRowResult]:
    # Keep the jobs search GIN pending list from repeatedly merging into its main
    # index during a large import. PostgreSQL still makes pending entries queryable;
    # autovacuum performs the eventual merge outside the import's critical path.
    await session.execute(text("SET LOCAL gin_pending_list_limit = '64MB'"))
    identities: list[_Identities] = []
    customer_writes: list[CustomerWrite] = []
    for item in items:
        record = item.record
        customer = customer_key(
            organization_id,
            source_system_id,
            external_id=record.customer_external_id,
            phone_e164=record.customer_phone_e164,
            name=record.customer_name,
            postal_code=record.postal_code,
        )
        if customer is None:
            raise ValueError("Validated row has no customer identity.")
        location = location_key(
            organization_id,
            source_system_id,
            external_id=record.location_external_id,
            customer_digest=customer.digest,
            address_line1=record.address_line1,
            postal_code=record.postal_code,
        )
        equipment = equipment_key(
            organization_id,
            source_system_id,
            external_id=record.equipment_external_id,
            serial_number=record.equipment_serial,
            location_digest=location.digest if location else None,
            manufacturer=record.equipment_manufacturer,
            model=record.equipment_model,
            equipment_type=record.equipment_type,
        )
        technician = technician_key(
            organization_id,
            source_system_id,
            external_id=record.technician_external_id,
            employee_code=record.technician_code,
            name=record.technician_name,
        )
        job = (
            external_job_key(organization_id, source_system_id, record.external_job_id)
            if record.external_job_id
            else job_key(
                organization_id,
                customer.digest,
                service_date=record.service_date,
                summary=record.summary,
                description=record.description,
                invoice_number=record.invoice_number,
            )
        )
        category_key = None
        if record.service_category:
            category_key = (
                normalize_name(record.service_category) or record.service_category
            ).replace(" ", "-")
        identities.append(
            _Identities(
                item=item,
                customer=customer.digest,
                location=location.digest if location else None,
                equipment=equipment.digest if equipment else None,
                technician=technician.digest if technician else None,
                job=job.digest,
                category_key=category_key,
            )
        )
        display_name = _label(
            record.customer_name,
            record.customer_external_id,
            record.customer_phone_raw,
            record.customer_phone_e164,
        )
        customer_writes.append(
            CustomerWrite(
                natural_key_hash=customer.digest,
                external_id=record.customer_external_id,
                display_name=display_name,
                normalized_name=normalize_name(display_name) or display_name.casefold(),
                email=record.customer_email,
                phone_raw=record.customer_phone_raw,
                phone_e164=record.customer_phone_e164,
            )
        )

    customers = await bulk_resolve_customers(
        session,
        organization_id=organization_id,
        source_system_id=source_system_id,
        writes=customer_writes,
    )
    locations = await bulk_resolve_locations(
        session,
        organization_id=organization_id,
        writes=[
            LocationWrite(
                customer_id=customers[identity.customer].id,
                address_hash=identity.location,
                external_id=identity.item.record.location_external_id,
                address_line1=identity.item.record.address_line1,
                city=identity.item.record.city,
                region=identity.item.record.region,
                postal_code=identity.item.record.postal_code,
            )
            for identity in identities
            if identity.location is not None
        ],
    )
    equipment_entities = await bulk_resolve_equipment(
        session,
        organization_id=organization_id,
        writes=[
            EquipmentWrite(
                customer_id=customers[identity.customer].id,
                location_id=(
                    locations[identity.location].id if identity.location is not None else None
                ),
                natural_key_hash=identity.equipment,
                external_id=identity.item.record.equipment_external_id,
                serial_number=identity.item.record.equipment_serial,
                manufacturer=identity.item.record.equipment_manufacturer,
                model=identity.item.record.equipment_model,
                equipment_type=identity.item.record.equipment_type,
            )
            for identity in identities
            if identity.equipment is not None
        ],
    )
    technicians = await bulk_resolve_technicians(
        session,
        organization_id=organization_id,
        writes=[
            TechnicianWrite(
                natural_key_hash=identity.technician,
                external_id=identity.item.record.technician_external_id,
                full_name=_label(
                    identity.item.record.technician_name,
                    identity.item.record.technician_code,
                    identity.item.record.technician_external_id,
                ),
                normalized_name=(
                    normalize_name(
                        _label(
                            identity.item.record.technician_name,
                            identity.item.record.technician_code,
                            identity.item.record.technician_external_id,
                        )
                    )
                    or _label(
                        identity.item.record.technician_name,
                        identity.item.record.technician_code,
                        identity.item.record.technician_external_id,
                    ).casefold()
                ),
                employee_code=identity.item.record.technician_code,
            )
            for identity in identities
            if identity.technician is not None
        ],
    )
    categories = await bulk_resolve_service_categories(
        session,
        organization_id=organization_id,
        writes=[
            ServiceCategoryWrite(
                key=identity.category_key,
                label=identity.item.record.service_category,
            )
            for identity in identities
            if identity.category_key is not None
            and identity.item.record.service_category is not None
        ],
    )
    jobs = await bulk_upsert_jobs(
        session,
        organization_id=organization_id,
        writes=[
            JobWrite(
                source_system_id=source_system_id,
                external_id=identity.item.record.external_job_id,
                natural_key_hash=identity.job,
                import_batch_id=batch_id,
                customer_id=customers[identity.customer].id,
                location_id=(
                    locations[identity.location].id if identity.location is not None else None
                ),
                equipment_id=(
                    equipment_entities[identity.equipment].id
                    if identity.equipment is not None
                    else None
                ),
                technician_id=(
                    technicians[identity.technician] if identity.technician is not None else None
                ),
                service_category_id=(
                    categories[identity.category_key] if identity.category_key is not None else None
                ),
                raw_service_category=identity.item.record.service_category,
                raw_job_type=identity.item.record.job_type,
                status=JobStatus(identity.item.record.job_status or JobStatus.UNKNOWN.value),
                scheduled_at=identity.item.record.scheduled_at,
                started_at=identity.item.record.started_at,
                completed_at=identity.item.record.completed_at,
                service_date=identity.item.record.service_date,
                duration_minutes=identity.item.record.duration_minutes,
                summary=identity.item.record.summary,
                description=identity.item.record.description,
                symptoms_text=identity.item.record.symptoms,
                diagnosis_text=identity.item.record.diagnosis,
                resolution_text=identity.item.record.resolution,
                invoice_number=identity.item.record.invoice_number,
                revenue_amount=identity.item.record.revenue_amount,
                parts_amount=identity.item.record.parts_amount,
                labor_amount=identity.item.record.labor_amount,
                currency_code=currency_code,
                is_warranty=identity.item.record.is_warranty,
                warranty_reference=identity.item.record.warranty_reference,
                extra_fields=dict(identity.item.record.extra_fields),
            )
            for identity in identities
        ],
    )
    await bulk_add_job_notes(
        session,
        organization_id=organization_id,
        notes=[
            (
                jobs[identity.job].job_id,
                identity.item.record.technician_notes,
                identity.item.record.technician_name,
                identity.item.record.completed_at,
            )
            for identity in identities
            if identity.item.record.technician_notes is not None
        ],
    )
    aggregates: dict[UUID, CustomerJobAggregate] = {}
    for identity in identities:
        customer_id = customers[identity.customer].id
        result = jobs[identity.job]
        seen_at = datetime.combine(
            identity.item.record.service_date, datetime.min.time(), tzinfo=UTC
        )
        current = aggregates.get(customer_id)
        if current is None:
            aggregates[customer_id] = CustomerJobAggregate(
                customer_id=customer_id,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                created_jobs=int(result.created),
            )
        else:
            aggregates[customer_id] = CustomerJobAggregate(
                customer_id=customer_id,
                first_seen_at=min(current.first_seen_at, seen_at),
                last_seen_at=max(current.last_seen_at, seen_at),
                created_jobs=current.created_jobs + int(result.created),
            )
    await bulk_register_customer_jobs(
        session,
        organization_id=organization_id,
        aggregates=list(aggregates.values()),
    )
    return [
        ChunkRowResult(
            row_number=identity.item.row_number,
            job_id=jobs[identity.job].job_id,
            created=jobs[identity.job].created,
            natural_key_collision=jobs[identity.job].natural_key_collision,
        )
        for identity in identities
    ]
