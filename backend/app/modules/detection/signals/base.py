"""Pure signal contracts. See docs/architecture/07-detection-engine.md §3."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import ClassVar, Protocol, TypeVar
from uuid import UUID

from app.modules.detection.schemas import SignalOutcome as SignalOutcome


class BaseSignal:
    key: ClassVar[str]


@dataclass(frozen=True, slots=True)
class JobSignalData:
    id: UUID
    customer_id: UUID | None
    location_id: UUID | None
    equipment_id: UUID | None
    technician_id: UUID | None
    service_category_id: UUID | None
    service_category: str | None
    raw_job_type: str | None
    service_date: date
    revenue_amount: Decimal | None
    is_warranty: bool
    extra_fields: Mapping[str, object]
    part_codes: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra_fields", MappingProxyType(dict(self.extra_fields)))


@dataclass(frozen=True, slots=True)
class CandidatePair:
    candidate_id: UUID
    prior: JobSignalData
    followup: JobSignalData
    days_between: int
    recurrence_count: int
    equipment_serial: str | None
    equipment_warranty_expires_on: date | None


@dataclass(frozen=True, slots=True)
class SignalResult:
    key: str
    outcome: SignalOutcome
    strength: Decimal
    raw_value: dict[str, object]
    explanation: str

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.strength <= Decimal(1):
            msg = "signal strength must be between 0 and 1"
            raise ValueError(msg)


CandidatePairT = TypeVar("CandidatePairT", contravariant=True)


class Signal(Protocol[CandidatePairT]):
    key: ClassVar[str]

    def evaluate(
        self,
        pair: CandidatePairT,
        params: dict[str, object],
    ) -> SignalResult: ...
