"""Public technician write boundary."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.workforce.models import Technician


@dataclass(frozen=True, slots=True)
class TechnicianWrite:
    natural_key_hash: bytes
    external_id: str | None
    full_name: str
    normalized_name: str
    employee_code: str | None


async def bulk_resolve_technicians(
    session: AsyncSession,
    *,
    organization_id: UUID,
    writes: list[TechnicianWrite],
) -> dict[bytes, UUID]:
    unique = {item.natural_key_hash: item for item in writes}
    if not unique:
        return {}
    lock_keys = sorted(f"{organization_id}:technician:{digest.hex()}" for digest in unique)
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
            "external_id": item.external_id,
            "natural_key_hash": item.natural_key_hash,
            "full_name": item.full_name,
            "normalized_name": item.normalized_name,
            "employee_code": item.employee_code,
        }
        for item in unique.values()
    ]
    statement = insert(Technician)
    excluded = statement.excluded
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Technician.organization_id, Technician.natural_key_hash],
            index_where=Technician.deleted_at.is_(None),
            set_={
                "external_id": func.coalesce(Technician.external_id, excluded.external_id),
                "employee_code": func.coalesce(Technician.employee_code, excluded.employee_code),
                "updated_at": func.now(),
            },
        ),
        values,
    )
    rows = (
        await session.execute(
            select(Technician.id, Technician.natural_key_hash).where(
                Technician.organization_id == organization_id,
                Technician.natural_key_hash.in_(list(unique)),
                Technician.deleted_at.is_(None),
            )
        )
    ).all()
    return {digest: identifier for identifier, digest in rows}


async def resolve_technician(
    session: AsyncSession,
    *,
    organization_id: UUID,
    natural_key_hash: bytes,
    external_id: str | None,
    full_name: str,
    normalized_name: str,
    employee_code: str | None,
) -> UUID:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{organization_id}:technician:{natural_key_hash.hex()}"},
    )
    technician = (
        await session.execute(
            select(Technician).where(
                Technician.organization_id == organization_id,
                Technician.natural_key_hash == natural_key_hash,
                Technician.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if technician is None:
        technician = Technician(
            organization_id=organization_id,
            external_id=external_id,
            natural_key_hash=natural_key_hash,
            full_name=full_name,
            normalized_name=normalized_name,
            employee_code=employee_code,
        )
        session.add(technician)
        await session.flush()
    else:
        if technician.external_id is None and external_id is not None:
            technician.external_id = external_id
        if technician.employee_code is None and employee_code is not None:
            technician.employee_code = employee_code
    return technician.id
