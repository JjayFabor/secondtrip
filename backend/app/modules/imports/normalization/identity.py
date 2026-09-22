"""Single implementation of tenant-scoped natural-key derivation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from app.modules.imports.normalization.text import normalize_name, normalize_text


class IdentityStrategy(StrEnum):
    EXTERNAL_ID = "external_id"
    PHONE = "phone"
    NAME_POSTAL = "name_postal"
    NAME_ONLY = "name_only"
    ADDRESS = "address"
    SERIAL_NUMBER = "serial_number"
    EQUIPMENT_ATTRIBUTES = "equipment_attributes"
    EMPLOYEE_CODE = "employee_code"
    NORMALIZED_NAME = "normalized_name"
    JOB_NATURAL_KEY = "job_natural_key"


@dataclass(frozen=True, slots=True)
class NaturalKey:
    digest: bytes
    strategy: IdentityStrategy
    low_confidence: bool = False


def _digest(*parts: object) -> bytes:
    return hashlib.sha256("|".join(str(part) for part in parts).encode()).digest()


def customer_key(
    organization_id: UUID,
    source_system_id: UUID,
    *,
    external_id: str | None,
    phone_e164: str | None,
    name: str | None,
    postal_code: str | None,
) -> NaturalKey | None:
    if external_id:
        return NaturalKey(
            _digest(organization_id, source_system_id, external_id), IdentityStrategy.EXTERNAL_ID
        )
    if phone_e164:
        return NaturalKey(_digest(organization_id, phone_e164), IdentityStrategy.PHONE)
    normalized = normalize_name(name)
    if normalized and postal_code:
        return NaturalKey(
            _digest(organization_id, normalized, postal_code.strip().casefold()),
            IdentityStrategy.NAME_POSTAL,
        )
    if normalized:
        return NaturalKey(_digest(organization_id, normalized), IdentityStrategy.NAME_ONLY, True)
    return None


def location_key(
    organization_id: UUID,
    source_system_id: UUID,
    *,
    external_id: str | None,
    customer_digest: bytes | None,
    address_line1: str | None,
    postal_code: str | None,
) -> NaturalKey | None:
    if external_id:
        return NaturalKey(
            _digest(organization_id, source_system_id, external_id), IdentityStrategy.EXTERNAL_ID
        )
    address = normalize_text(address_line1).value
    if customer_digest and address and postal_code:
        return NaturalKey(
            _digest(
                organization_id,
                customer_digest.hex(),
                address.casefold(),
                postal_code.strip().casefold(),
            ),
            IdentityStrategy.ADDRESS,
        )
    return None


def equipment_key(
    organization_id: UUID,
    source_system_id: UUID,
    *,
    external_id: str | None,
    serial_number: str | None,
    location_digest: bytes | None,
    manufacturer: str | None,
    model: str | None,
    equipment_type: str | None,
) -> NaturalKey | None:
    if external_id:
        return NaturalKey(
            _digest(organization_id, source_system_id, external_id), IdentityStrategy.EXTERNAL_ID
        )
    if serial_number:
        return NaturalKey(
            _digest(organization_id, serial_number.strip().upper()), IdentityStrategy.SERIAL_NUMBER
        )
    attributes = [normalize_text(item).value for item in (manufacturer, model, equipment_type)]
    if location_digest and all(attributes):
        return NaturalKey(
            _digest(
                organization_id,
                location_digest.hex(),
                *(item.casefold() for item in attributes if item),
            ),
            IdentityStrategy.EQUIPMENT_ATTRIBUTES,
        )
    return None


def technician_key(
    organization_id: UUID,
    source_system_id: UUID,
    *,
    external_id: str | None,
    employee_code: str | None,
    name: str | None,
) -> NaturalKey | None:
    if external_id:
        return NaturalKey(
            _digest(organization_id, source_system_id, external_id), IdentityStrategy.EXTERNAL_ID
        )
    if employee_code:
        return NaturalKey(
            _digest(organization_id, employee_code.strip().casefold()),
            IdentityStrategy.EMPLOYEE_CODE,
        )
    normalized = normalize_name(name)
    if normalized:
        return NaturalKey(
            _digest(organization_id, normalized), IdentityStrategy.NORMALIZED_NAME, True
        )
    return None


def job_key(
    organization_id: UUID,
    customer_digest: bytes,
    *,
    service_date: date,
    summary: str | None,
    description: str | None,
    invoice_number: str | None,
) -> NaturalKey:
    narrative = normalize_text(summary or description).value or ""
    return NaturalKey(
        _digest(
            organization_id,
            customer_digest.hex(),
            service_date.isoformat(),
            narrative.casefold()[:200],
            (invoice_number or "").strip().casefold(),
        ),
        IdentityStrategy.JOB_NATURAL_KEY,
    )


def external_job_key(
    organization_id: UUID, source_system_id: UUID, external_id: str
) -> NaturalKey:
    """Populate the mandatory job hash without colliding across external identities."""
    return NaturalKey(
        _digest(organization_id, source_system_id, external_id), IdentityStrategy.EXTERNAL_ID
    )
