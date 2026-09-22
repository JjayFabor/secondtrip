"""Canonical job-pair ordering. This is the only Python pair constructor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Protocol
from uuid import UUID


class PairableJob(Protocol):
    @property
    def id(self) -> UUID: ...

    @property
    def service_date(self) -> date: ...

    @property
    def started_at(self) -> datetime | None: ...


@dataclass(frozen=True, slots=True)
class CanonicalPair[PairableJobT: PairableJob]:
    prior: PairableJobT
    followup: PairableJobT

    @property
    def days_between(self) -> int:
        return (self.followup.service_date - self.prior.service_date).days


def canonical_pair[PairableJobT: PairableJob](
    first: PairableJobT,
    second: PairableJobT,
) -> CanonicalPair[PairableJobT]:
    """Order jobs by `(service_date, COALESCE(started_at, date), id)`."""

    if first.id == second.id:
        msg = "a candidate pair must contain two different jobs"
        raise ValueError(msg)
    if _ordering_key(first) < _ordering_key(second):
        return CanonicalPair(prior=first, followup=second)
    return CanonicalPair(prior=second, followup=first)


def _ordering_key(job: PairableJob) -> tuple[date, datetime, UUID]:
    order_time = job.started_at or datetime.combine(job.service_date, time.min, tzinfo=UTC)
    if order_time.tzinfo is None or order_time.utcoffset() is None:
        msg = "started_at must be timezone-aware"
        raise ValueError(msg)
    return (job.service_date, order_time, job.id)
