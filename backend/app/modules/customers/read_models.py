"""Narrow customer and equipment projections for candidate review."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customers.models import Customer, Equipment


@dataclass(frozen=True, slots=True)
class CandidateCustomer:
    id: UUID
    display_name: str
    account_number: str | None


@dataclass(frozen=True, slots=True)
class CandidateEquipment:
    id: UUID
    asset_tag: str | None
    serial_number: str | None
    manufacturer: str | None
    model: str | None
    equipment_type: str | None


async def load_candidate_customers(
    session: AsyncSession,
    *,
    organization_id: UUID,
    customer_ids: set[UUID],
) -> dict[UUID, CandidateCustomer]:
    if not customer_ids:
        return {}
    rows = (
        await session.execute(
            select(Customer.id, Customer.display_name, Customer.account_number).where(
                Customer.organization_id == organization_id,
                Customer.id.in_(customer_ids),
            )
        )
    ).all()
    return {row.id: CandidateCustomer(*row) for row in rows}


async def load_candidate_equipment(
    session: AsyncSession,
    *,
    organization_id: UUID,
    equipment_ids: set[UUID],
) -> dict[UUID, CandidateEquipment]:
    if not equipment_ids:
        return {}
    rows = (
        await session.execute(
            select(
                Equipment.id,
                Equipment.asset_tag,
                Equipment.serial_number,
                Equipment.manufacturer,
                Equipment.model,
                Equipment.equipment_type,
            ).where(
                Equipment.organization_id == organization_id,
                Equipment.id.in_(equipment_ids),
            )
        )
    ).all()
    return {row.id: CandidateEquipment(*row) for row in rows}
