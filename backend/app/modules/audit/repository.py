"""Tenant-scoped audit reads."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import decode_cursor, encode_cursor
from app.modules.audit.models import AuditEvent


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_events(
        self,
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
        statement = select(AuditEvent).where(AuditEvent.organization_id == organization_id)
        if action is not None:
            statement = statement.where(AuditEvent.action == action)
        if actor_user_id is not None:
            statement = statement.where(AuditEvent.actor_user_id == actor_user_id)
        if resource_type is not None:
            statement = statement.where(AuditEvent.resource_type == resource_type)
        if resource_id is not None:
            statement = statement.where(AuditEvent.resource_id == resource_id)
        if occurred_from is not None:
            statement = statement.where(AuditEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            statement = statement.where(AuditEvent.occurred_at < occurred_to)
        if cursor is not None:
            sort_value, cursor_id = decode_cursor(cursor)
            occurred_at = datetime.fromisoformat(str(sort_value).replace("Z", "+00:00"))
            statement = statement.where(
                or_(
                    AuditEvent.occurred_at < occurred_at,
                    and_(AuditEvent.occurred_at == occurred_at, AuditEvent.id < cursor_id),
                )
            )

        statement = statement.order_by(desc(AuditEvent.occurred_at), desc(AuditEvent.id)).limit(
            limit + 1
        )
        result = await self._session.execute(statement)
        rows = list(result.scalars().all())
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = encode_cursor(sort_value=last.occurred_at, id=last.id)
        return rows, next_cursor
