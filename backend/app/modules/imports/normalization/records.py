"""Canonical record boundary shared by CSV and future source adapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Normalized service-job data with no CSV or transport concepts."""

    service_date: date
    external_job_id: str | None = None
    customer_name: str | None = None
    customer_external_id: str | None = None
    customer_phone_raw: str | None = None
    customer_phone_e164: str | None = None
    customer_email: str | None = None
    address_line1: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    location_external_id: str | None = None
    equipment_serial: str | None = None
    equipment_manufacturer: str | None = None
    equipment_model: str | None = None
    equipment_type: str | None = None
    equipment_external_id: str | None = None
    technician_name: str | None = None
    technician_external_id: str | None = None
    technician_code: str | None = None
    service_category: str | None = None
    job_type: str | None = None
    job_status: str | None = None
    summary: str | None = None
    description: str | None = None
    symptoms: str | None = None
    diagnosis: str | None = None
    resolution: str | None = None
    technician_notes: str | None = None
    invoice_number: str | None = None
    revenue_amount: Decimal | None = None
    parts_amount: Decimal | None = None
    labor_amount: Decimal | None = None
    duration_minutes: int | None = None
    is_warranty: bool = False
    warranty_reference: str | None = None
    scheduled_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    extra_fields: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        object.__setattr__(self, "extra_fields", MappingProxyType(dict(self.extra_fields)))


def serialize_source_record(record: SourceRecord) -> dict[str, object]:
    payload: dict[str, object] = {}
    for item in fields(record):
        value = getattr(record, item.name)
        if isinstance(value, (date, datetime, Decimal)):
            payload[item.name] = str(value)
        elif item.name == "extra_fields":
            payload[item.name] = dict(value)
        else:
            payload[item.name] = value
    return payload


def deserialize_source_record(payload: dict[str, object]) -> SourceRecord:
    values = dict(payload)
    values["service_date"] = date.fromisoformat(str(values["service_date"]))
    for name in ("scheduled_at", "started_at", "completed_at"):
        if values.get(name) is not None:
            values[name] = datetime.fromisoformat(str(values[name]))
    for name in ("revenue_amount", "parts_amount", "labor_amount"):
        if values.get(name) is not None:
            values[name] = Decimal(str(values[name]))
    return SourceRecord(**cast(dict[str, Any], values))
