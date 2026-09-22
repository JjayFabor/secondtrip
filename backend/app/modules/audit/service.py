"""Audit service — see docs/architecture/13-audit.md.

Leaf infrastructure: every module may call this, it calls nothing except
core/db. `record()` is always called from within the SAME transaction as
the change it describes (CLAUDE.md's transaction-boundary rule) — pass it
the already-open session rather than opening a new one, so a rollback of
the calling operation rolls back its audit row too.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.allowlist import sanitize_changes
from app.modules.audit.models import AuditEvent
from app.modules.audit.repository import AuditRepository
from app.modules.audit.schemas import ActorType


async def record(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action: str,
    summary: str,
    actor_type: ActorType = ActorType.USER,
    actor_user_id: UUID | None = None,
    actor_label: str = "",
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    changes: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    session.add(
        AuditEvent(
            organization_id=organization_id,
            actor_type=actor_type.value,
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=summary,
            changes=sanitize_changes(resource_type, changes),
            request_id=request_id,
        )
    )


async def list_events(
    session: AsyncSession,
    *,
    organization_id: UUID,
    action: str | None = None,
    actor_user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    cursor: str | None = None,
    limit: int,
) -> tuple[list[AuditEvent], str | None]:
    """Public read boundary for tenant audit history."""
    return await AuditRepository(session).list_events(
        organization_id=organization_id,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        cursor=cursor,
        limit=limit,
    )
