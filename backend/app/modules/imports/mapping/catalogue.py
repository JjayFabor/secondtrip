"""Canonical fields accepted by source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class TargetType(StrEnum):
    TEXT = "text"
    DATE = "date"
    DATETIME = "datetime"
    MONEY = "money"
    INTEGER = "integer"
    BOOLEAN = "boolean"


@dataclass(frozen=True, slots=True)
class TargetField:
    name: str
    data_type: TargetType
    required: bool = False


def _field(
    name: str, data_type: TargetType = TargetType.TEXT, *, required: bool = False
) -> TargetField:
    return TargetField(name=name, data_type=data_type, required=required)


TARGET_FIELDS: Final[dict[str, TargetField]] = {
    field.name: field
    for field in (
        _field("external_job_id"),
        _field("service_date", TargetType.DATE, required=True),
        _field("customer_name"),
        _field("customer_external_id"),
        _field("customer_phone"),
        _field("customer_email"),
        _field("address_line1"),
        _field("city"),
        _field("region"),
        _field("postal_code"),
        _field("location_external_id"),
        _field("equipment_serial"),
        _field("equipment_manufacturer"),
        _field("equipment_model"),
        _field("equipment_type"),
        _field("equipment_external_id"),
        _field("technician_name"),
        _field("technician_external_id"),
        _field("technician_code"),
        _field("service_category"),
        _field("job_type"),
        _field("job_status"),
        _field("summary"),
        _field("description"),
        _field("symptoms"),
        _field("diagnosis"),
        _field("resolution"),
        _field("technician_notes"),
        _field("invoice_number"),
        _field("revenue_amount", TargetType.MONEY),
        _field("parts_amount", TargetType.MONEY),
        _field("labor_amount", TargetType.MONEY),
        _field("duration_minutes", TargetType.INTEGER),
        _field("is_warranty", TargetType.BOOLEAN),
        _field("warranty_reference"),
        _field("scheduled_at", TargetType.DATETIME),
        _field("started_at", TargetType.DATETIME),
        _field("completed_at", TargetType.DATETIME),
    )
}
