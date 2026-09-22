"""Transactional HTTP idempotency for mutation endpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.modules.idempotency.models import ApiIdempotencyRecord


class IdempotencyConflictError(ConflictError):
    code = "IDEMPOTENCY_KEY_CONFLICT"
    title = "Idempotency key conflict"


@dataclass(frozen=True, slots=True)
class IdempotencyClaim:
    record: ApiIdempotencyRecord
    replay_body: dict[str, object] | None
    replay_status: int | None


def request_digest(payload: dict[str, object]) -> bytes:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).digest()


async def claim(
    session: AsyncSession,
    *,
    organization_id: UUID,
    route: str,
    idempotency_key: str,
    digest: bytes,
    ttl_hours: int = 24,
) -> IdempotencyClaim:
    """Claim a key under an advisory lock, or return its completed response."""
    lock_key = f"{organization_id}:{route}:{idempotency_key}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    )
    now = datetime.now(UTC)
    record = (
        await session.execute(
            select(ApiIdempotencyRecord).where(
                ApiIdempotencyRecord.organization_id == organization_id,
                ApiIdempotencyRecord.route == route,
                ApiIdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if record is not None and record.expires_at <= now:
        await session.execute(
            delete(ApiIdempotencyRecord).where(ApiIdempotencyRecord.id == record.id)
        )
        record = None
    if record is not None:
        if record.request_hash != digest:
            raise IdempotencyConflictError(
                "This idempotency key was already used for a different request."
            )
        if record.response_status is None or record.response_body is None:
            raise IdempotencyConflictError("The original request is still being processed.")
        return IdempotencyClaim(record, record.response_body, record.response_status)

    record = ApiIdempotencyRecord(
        organization_id=organization_id,
        route=route,
        idempotency_key=idempotency_key,
        request_hash=digest,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    session.add(record)
    await session.flush()
    return IdempotencyClaim(record, None, None)


def complete(
    claim_result: IdempotencyClaim,
    *,
    status_code: int,
    response_body: dict[str, object],
    response_headers: dict[str, str] | None = None,
) -> None:
    claim_result.record.response_status = status_code
    claim_result.record.response_body = response_body
    claim_result.record.response_headers = response_headers or {}
