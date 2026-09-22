"""Public customer, location, and equipment write boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.customers.models import Customer, Equipment, Location


@dataclass(frozen=True, slots=True)
class ResolvedEntity:
    id: UUID
    natural_key_hash: bytes


@dataclass(frozen=True, slots=True)
class CustomerWrite:
    natural_key_hash: bytes
    external_id: str | None
    display_name: str
    normalized_name: str
    email: str | None
    phone_raw: str | None
    phone_e164: str | None


@dataclass(frozen=True, slots=True)
class LocationWrite:
    customer_id: UUID
    address_hash: bytes
    external_id: str | None
    address_line1: str | None
    city: str | None
    region: str | None
    postal_code: str | None


@dataclass(frozen=True, slots=True)
class EquipmentWrite:
    customer_id: UUID
    location_id: UUID | None
    natural_key_hash: bytes
    external_id: str | None
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    equipment_type: str | None


@dataclass(frozen=True, slots=True)
class CustomerJobAggregate:
    customer_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    created_jobs: int


@dataclass(frozen=True, slots=True)
class EquipmentDetectionData:
    serial_number: str | None
    warranty_expires_on: date | None


async def get_equipment_detection_data(
    session: AsyncSession,
    *,
    organization_id: UUID,
    equipment_ids: set[UUID],
) -> dict[UUID, EquipmentDetectionData]:
    """Public read boundary for the detection engine's equipment signals."""
    if not equipment_ids:
        return {}
    rows = (
        await session.execute(
            select(Equipment.id, Equipment.serial_number, Equipment.warranty_expires_on).where(
                Equipment.organization_id == organization_id,
                Equipment.id.in_(equipment_ids),
            )
        )
    ).all()
    return {
        equipment_id: EquipmentDetectionData(serial_number, warranty_expires_on)
        for equipment_id, serial_number, warranty_expires_on in rows
    }


async def _lock_many(
    session: AsyncSession, organization_id: UUID, kind: str, digests: list[bytes]
) -> None:
    keys = sorted(f"{organization_id}:{kind}:{digest.hex()}" for digest in set(digests))
    if keys:
        await session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(lock_key, 0)) "
                "FROM unnest(CAST(:lock_keys AS text[])) AS lock_key ORDER BY lock_key"
            ),
            {"lock_keys": keys},
        )


async def bulk_resolve_customers(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_system_id: UUID,
    writes: list[CustomerWrite],
) -> dict[bytes, ResolvedEntity]:
    unique = {item.natural_key_hash: item for item in writes}
    if not unique:
        return {}
    await _lock_many(session, organization_id, "customer", list(unique))
    values = [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "source_system_id": source_system_id,
            "external_id": item.external_id,
            "natural_key_hash": item.natural_key_hash,
            "display_name": item.display_name,
            "normalized_name": item.normalized_name,
            "email": item.email,
            "phone_raw": item.phone_raw,
            "phone_e164": item.phone_e164,
        }
        for item in unique.values()
    ]
    statement = insert(Customer)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Customer.organization_id, Customer.natural_key_hash],
            index_where=Customer.deleted_at.is_(None),
            set_={
                "source_system_id": func.coalesce(
                    Customer.source_system_id, excluded.source_system_id
                ),
                "external_id": func.coalesce(Customer.external_id, excluded.external_id),
                "email": func.coalesce(Customer.email, excluded.email),
                "phone_raw": func.coalesce(Customer.phone_raw, excluded.phone_raw),
                "phone_e164": func.coalesce(Customer.phone_e164, excluded.phone_e164),
                "updated_at": func.now(),
            },
        ),
        values,
    )
    rows = (
        await session.execute(
            select(Customer.id, Customer.natural_key_hash).where(
                Customer.organization_id == organization_id,
                Customer.natural_key_hash.in_(list(unique)),
                Customer.deleted_at.is_(None),
            )
        )
    ).all()
    return {digest: ResolvedEntity(identifier, digest) for identifier, digest in rows}


async def bulk_resolve_locations(
    session: AsyncSession,
    *,
    organization_id: UUID,
    writes: list[LocationWrite],
) -> dict[bytes, ResolvedEntity]:
    unique = {item.address_hash: item for item in writes}
    if not unique:
        return {}
    await _lock_many(session, organization_id, "location", list(unique))
    values = [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "customer_id": item.customer_id,
            "external_id": item.external_id,
            "address_hash": item.address_hash,
            "address_line1": item.address_line1,
            "city": item.city,
            "region": item.region,
            "postal_code": item.postal_code,
        }
        for item in unique.values()
    ]
    statement = insert(Location)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[
                Location.organization_id,
                Location.customer_id,
                Location.address_hash,
            ],
            index_where=Location.deleted_at.is_(None),
            set_={
                "external_id": func.coalesce(Location.external_id, excluded.external_id),
                "address_line1": func.coalesce(Location.address_line1, excluded.address_line1),
                "city": func.coalesce(Location.city, excluded.city),
                "region": func.coalesce(Location.region, excluded.region),
                "postal_code": func.coalesce(Location.postal_code, excluded.postal_code),
                "updated_at": func.now(),
            },
        ),
        values,
    )
    rows = (
        await session.execute(
            select(Location.id, Location.address_hash).where(
                Location.organization_id == organization_id,
                Location.address_hash.in_(list(unique)),
                Location.deleted_at.is_(None),
            )
        )
    ).all()
    return {digest: ResolvedEntity(identifier, digest) for identifier, digest in rows}


async def bulk_resolve_equipment(
    session: AsyncSession,
    *,
    organization_id: UUID,
    writes: list[EquipmentWrite],
) -> dict[bytes, ResolvedEntity]:
    unique = {item.natural_key_hash: item for item in writes}
    if not unique:
        return {}
    await _lock_many(session, organization_id, "equipment", list(unique))
    values = [
        {
            "id": new_id(),
            "organization_id": organization_id,
            "customer_id": item.customer_id,
            "location_id": item.location_id,
            "external_id": item.external_id,
            "natural_key_hash": item.natural_key_hash,
            "serial_number": item.serial_number,
            "manufacturer": item.manufacturer,
            "model": item.model,
            "equipment_type": item.equipment_type,
        }
        for item in unique.values()
    ]
    statement = insert(Equipment)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Equipment.organization_id, Equipment.natural_key_hash],
            index_where=Equipment.deleted_at.is_(None),
            set_={
                "customer_id": func.coalesce(Equipment.customer_id, excluded.customer_id),
                "location_id": func.coalesce(Equipment.location_id, excluded.location_id),
                "external_id": func.coalesce(Equipment.external_id, excluded.external_id),
                "serial_number": func.coalesce(Equipment.serial_number, excluded.serial_number),
                "manufacturer": func.coalesce(Equipment.manufacturer, excluded.manufacturer),
                "model": func.coalesce(Equipment.model, excluded.model),
                "equipment_type": func.coalesce(Equipment.equipment_type, excluded.equipment_type),
                "updated_at": func.now(),
            },
        ),
        values,
    )
    rows = (
        await session.execute(
            select(Equipment.id, Equipment.natural_key_hash).where(
                Equipment.organization_id == organization_id,
                Equipment.natural_key_hash.in_(list(unique)),
                Equipment.deleted_at.is_(None),
            )
        )
    ).all()
    return {digest: ResolvedEntity(identifier, digest) for identifier, digest in rows}


async def bulk_register_customer_jobs(
    session: AsyncSession,
    *,
    organization_id: UUID,
    aggregates: list[CustomerJobAggregate],
) -> None:
    if not aggregates:
        return
    await session.execute(
        text(
            "UPDATE customers AS customer SET "
            "first_seen_job_at = LEAST(COALESCE(customer.first_seen_job_at, data.first_seen_at), "
            "data.first_seen_at), "
            "last_seen_job_at = GREATEST(COALESCE(customer.last_seen_job_at, data.last_seen_at), "
            "data.last_seen_at), "
            "job_count = customer.job_count + data.created_jobs, "
            "updated_at = now() "
            "FROM unnest(CAST(:customer_ids AS uuid[]), "
            "CAST(:first_seen AS timestamptz[]), CAST(:last_seen AS timestamptz[]), "
            "CAST(:created_jobs AS integer[])) "
            "AS data(customer_id, first_seen_at, last_seen_at, created_jobs) "
            "WHERE customer.organization_id = :organization_id "
            "AND customer.id = data.customer_id"
        ),
        {
            "organization_id": organization_id,
            "customer_ids": [item.customer_id for item in aggregates],
            "first_seen": [item.first_seen_at for item in aggregates],
            "last_seen": [item.last_seen_at for item in aggregates],
            "created_jobs": [item.created_jobs for item in aggregates],
        },
    )


async def _lock(session: AsyncSession, organization_id: UUID, kind: str, digest: bytes) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{organization_id}:{kind}:{digest.hex()}"},
    )


def _enrich(instance: object, **values: object | None) -> None:
    for name, value in values.items():
        if getattr(instance, name) is None and value is not None:
            setattr(instance, name, value)


async def resolve_customer(
    session: AsyncSession,
    *,
    organization_id: UUID,
    source_system_id: UUID,
    natural_key_hash: bytes,
    external_id: str | None,
    display_name: str,
    normalized_name: str,
    email: str | None,
    phone_raw: str | None,
    phone_e164: str | None,
) -> ResolvedEntity:
    await _lock(session, organization_id, "customer", natural_key_hash)
    customer = (
        await session.execute(
            select(Customer).where(
                Customer.organization_id == organization_id,
                Customer.natural_key_hash == natural_key_hash,
                Customer.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if customer is None:
        customer = Customer(
            organization_id=organization_id,
            source_system_id=source_system_id,
            external_id=external_id,
            natural_key_hash=natural_key_hash,
            display_name=display_name,
            normalized_name=normalized_name,
            email=email,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
        )
        session.add(customer)
        await session.flush()
    else:
        _enrich(
            customer,
            source_system_id=source_system_id,
            external_id=external_id,
            email=email,
            phone_raw=phone_raw,
            phone_e164=phone_e164,
        )
    return ResolvedEntity(customer.id, natural_key_hash)


async def resolve_location(
    session: AsyncSession,
    *,
    organization_id: UUID,
    customer_id: UUID,
    address_hash: bytes,
    external_id: str | None,
    address_line1: str | None,
    city: str | None,
    region: str | None,
    postal_code: str | None,
) -> ResolvedEntity:
    await _lock(session, organization_id, "location", address_hash)
    location = (
        await session.execute(
            select(Location).where(
                Location.organization_id == organization_id,
                Location.customer_id == customer_id,
                Location.address_hash == address_hash,
                Location.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if location is None:
        location = Location(
            organization_id=organization_id,
            customer_id=customer_id,
            external_id=external_id,
            address_hash=address_hash,
            address_line1=address_line1,
            city=city,
            region=region,
            postal_code=postal_code,
        )
        session.add(location)
        await session.flush()
    else:
        _enrich(
            location,
            external_id=external_id,
            address_line1=address_line1,
            city=city,
            region=region,
            postal_code=postal_code,
        )
    return ResolvedEntity(location.id, address_hash)


async def resolve_equipment(
    session: AsyncSession,
    *,
    organization_id: UUID,
    customer_id: UUID,
    location_id: UUID | None,
    natural_key_hash: bytes,
    external_id: str | None,
    serial_number: str | None,
    manufacturer: str | None,
    model: str | None,
    equipment_type: str | None,
) -> ResolvedEntity:
    await _lock(session, organization_id, "equipment", natural_key_hash)
    equipment = (
        await session.execute(
            select(Equipment).where(
                Equipment.organization_id == organization_id,
                Equipment.natural_key_hash == natural_key_hash,
                Equipment.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if equipment is None:
        equipment = Equipment(
            organization_id=organization_id,
            customer_id=customer_id,
            location_id=location_id,
            external_id=external_id,
            natural_key_hash=natural_key_hash,
            serial_number=serial_number,
            manufacturer=manufacturer,
            model=model,
            equipment_type=equipment_type,
        )
        session.add(equipment)
        await session.flush()
    else:
        _enrich(
            equipment,
            customer_id=customer_id,
            location_id=location_id,
            external_id=external_id,
            serial_number=serial_number,
            manufacturer=manufacturer,
            model=model,
            equipment_type=equipment_type,
        )
    return ResolvedEntity(equipment.id, natural_key_hash)


async def register_customer_job(
    session: AsyncSession,
    *,
    organization_id: UUID,
    customer_id: UUID,
    service_date: date,
    created: bool,
) -> None:
    customer = (
        await session.execute(
            select(Customer).where(
                Customer.organization_id == organization_id,
                Customer.id == customer_id,
                Customer.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    seen_at = datetime.combine(service_date, datetime.min.time(), tzinfo=UTC)
    if customer.first_seen_job_at is None or customer.first_seen_job_at > seen_at:
        customer.first_seen_job_at = seen_at
    if customer.last_seen_job_at is None or customer.last_seen_job_at < seen_at:
        customer.last_seen_job_at = seen_at
    if created:
        customer.job_count += 1
