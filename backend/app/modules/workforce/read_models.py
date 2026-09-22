"""Narrow workforce projections for candidate review."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workforce.models import Technician


async def load_candidate_technician_names(
    session: AsyncSession,
    *,
    organization_id: UUID,
    technician_ids: set[UUID],
) -> dict[UUID, str]:
    if not technician_ids:
        return {}
    rows = (
        await session.execute(
            select(Technician.id, Technician.full_name).where(
                Technician.organization_id == organization_id,
                Technician.id.in_(technician_ids),
            )
        )
    ).all()
    return {row.id: row.full_name for row in rows}
