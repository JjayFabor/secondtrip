"""Phone normalization while retaining the original value."""

from __future__ import annotations

from dataclasses import dataclass

import phonenumbers


@dataclass(frozen=True, slots=True)
class NormalizedPhone:
    raw: str | None
    e164: str | None


def normalize_phone(raw: str | None, *, default_region: str) -> NormalizedPhone:
    if raw is None or not raw.strip():
        return NormalizedPhone(raw=raw, e164=None)
    retained = raw.strip()
    try:
        parsed = phonenumbers.parse(retained, default_region.upper())
    except phonenumbers.NumberParseException:
        return NormalizedPhone(raw=retained, e164=None)
    if not phonenumbers.is_valid_number(parsed):
        return NormalizedPhone(raw=retained, e164=None)
    return NormalizedPhone(
        raw=retained,
        e164=phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164),
    )
