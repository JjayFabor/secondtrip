from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActorType(StrEnum):
    USER = "user"
    SYSTEM = "system"
    API_KEY = "api_key"


class AuditEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    actor_type: ActorType
    actor_user_id: UUID | None
    actor_label: str
    action: str
    resource_type: str | None
    resource_id: UUID | None
    summary: str
    changes: dict[str, object] | None
    request_id: str | None
    occurred_at: datetime


class AuditPageOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None
    has_more: bool
    limit: int


class AuditListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: list[AuditEventOut]
    page: AuditPageOut
