from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.core.pagination import (
    MAX_LIMIT,
    InvalidCursorError,
    clamp_limit,
    decode_cursor,
    encode_cursor,
)


def test_cursor_round_trips_a_uuid_sort_value() -> None:
    id_ = uuid4()
    cursor = encode_cursor(sort_value="2026-03-12", id=id_)
    sort_value, decoded_id = decode_cursor(cursor)
    assert sort_value == "2026-03-12"
    assert decoded_id == id_


def test_cursor_round_trips_a_datetime_sort_value() -> None:
    id_ = uuid4()
    when = datetime(2026, 3, 12, 10, 30, tzinfo=UTC)
    cursor = encode_cursor(sort_value=when, id=id_)
    sort_value, decoded_id = decode_cursor(cursor)
    assert sort_value == when.isoformat()
    assert decoded_id == id_


def test_malformed_cursor_raises_invalid_cursor_error() -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-valid-base64!!!")


def test_clamp_limit_defaults_and_bounds() -> None:
    assert clamp_limit(None) == 50
    assert clamp_limit(0) == 1
    assert clamp_limit(-5) == 1
    assert clamp_limit(10_000) == MAX_LIMIT
    assert clamp_limit(75) == 75
