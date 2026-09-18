"""Cursor pagination — see docs/architecture/15-api-design.md §1.

Offset pagination is wrong for tables actively being imported into: a
concurrent write shifts rows under an offset reader, silently duplicating
or skipping records. The cursor is the sort key plus a tie-breaking id,
base64-encoded, matching the composite index for that sort order.
"""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


class InvalidCursorError(ValueError):
    pass


def encode_cursor(*, sort_value: Any, id: UUID) -> str:
    payload = {"s": _jsonable(sort_value), "i": str(id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[Any, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw)
        return payload["s"], UUID(payload["i"])
    except Exception as exc:
        # Any malformed cursor is the same error to the caller — base64,
        # JSON, key-lookup and UUID-parse failures all collapse to one.
        raise InvalidCursorError("Cursor is malformed or expired.") from exc


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value
