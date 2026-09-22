from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from app.modules.detection.pairing import canonical_pair


@dataclass(frozen=True)
class JobStub:
    id: UUID
    service_date: date
    started_at: datetime | None = None


def job(
    identifier: int,
    service_date: date,
    started_at: datetime | None = None,
) -> JobStub:
    return JobStub(id=UUID(int=identifier), service_date=service_date, started_at=started_at)


def test_pair_orders_by_service_date_independent_of_argument_order() -> None:
    earlier = job(2, date(2026, 3, 1))
    later = job(1, date(2026, 3, 8))

    forward = canonical_pair(earlier, later)
    reverse = canonical_pair(later, earlier)

    assert forward == reverse
    assert forward.prior == earlier
    assert forward.followup == later
    assert forward.days_between == 7


def test_same_day_pair_uses_started_at_then_id_as_total_order() -> None:
    service_date = date(2026, 3, 1)
    later = job(1, service_date, datetime(2026, 3, 1, 11, tzinfo=UTC))
    earlier = job(9, service_date, datetime(2026, 3, 1, 9, tzinfo=UTC))

    pair = canonical_pair(later, earlier)

    assert pair.prior == earlier
    assert pair.followup == later


def test_null_started_at_uses_service_date_midnight() -> None:
    service_date = date(2026, 3, 1)
    without_start = job(9, service_date)
    with_start = job(1, service_date, datetime(2026, 3, 1, 9, tzinfo=UTC))

    assert canonical_pair(with_start, without_start).prior == without_start


def test_ids_break_an_otherwise_equal_ordering_tie() -> None:
    service_date = date(2026, 3, 1)
    higher_id = job(2, service_date)
    lower_id = job(1, service_date)

    assert canonical_pair(higher_id, lower_id).prior == lower_id


def test_pair_rejects_the_same_job() -> None:
    same_job = job(1, date(2026, 3, 1))

    with pytest.raises(ValueError, match="two different jobs"):
        canonical_pair(same_job, same_job)


def test_pair_rejects_naive_started_at() -> None:
    first = job(1, date(2026, 3, 1), datetime(2026, 3, 1, 9))
    second = job(2, date(2026, 3, 2))

    with pytest.raises(ValueError, match="timezone-aware"):
        canonical_pair(first, second)
