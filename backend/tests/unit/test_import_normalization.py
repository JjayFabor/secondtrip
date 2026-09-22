from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.imports.issues import IssueCode, IssueSeverity
from app.modules.imports.normalization.booleans import normalize_boolean
from app.modules.imports.normalization.dates import (
    DateOrder,
    infer_date_order,
    normalize_date,
    normalize_datetime,
)
from app.modules.imports.normalization.identity import (
    IdentityStrategy,
    customer_key,
    equipment_key,
    job_key,
)
from app.modules.imports.normalization.money import normalize_money
from app.modules.imports.normalization.phones import normalize_phone
from app.modules.imports.normalization.records import SourceRecord
from app.modules.imports.normalization.text import normalize_name, normalize_text

ORG_ID = UUID("018f0000-0000-7000-8000-000000000001")
OTHER_ORG_ID = UUID("018f0000-0000-7000-8000-000000000002")
SOURCE_ID = UUID("018f0000-0000-7000-8000-000000000003")


def test_text_normalization_preserves_content_but_removes_controls() -> None:
    result = normalize_text("  Cafe\u0301 \u202e  < 60F\nnext\tcolumn  ")
    assert result.value == "Café < 60F\nnext\tcolumn"
    assert result.issues == ()
    assert normalize_name("  ACME, Incorporated. ") == "acme"


def test_text_is_byte_capped_with_a_stable_warning() -> None:
    result = normalize_text("é" * 100, max_bytes=32)
    assert result.value is not None
    assert len(result.value.encode()) <= 32
    assert result.value.endswith("… [truncated]")
    assert result.issues[0].code is IssueCode.FIELD_TOO_LONG


@pytest.mark.parametrize("raw", ["Y", "yes", "TRUE", "1", "x", "Warranty"])
def test_boolean_true_values(raw: str) -> None:
    assert normalize_boolean(raw).value is True


def test_unknown_boolean_warns_and_uses_false() -> None:
    result = normalize_boolean("perhaps")
    assert result.value is False
    assert result.issues[0].severity is IssueSeverity.WARNING
    assert result.issues[0].raw_value == "perhaps"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("(1,234.56)", Decimal("-1234.56")),
        ("1,23,456.78", Decimal("123456.78")),
        ("12.345", Decimal("12345")),
        ("N/A", None),
        ("-", None),
    ],
)
def test_money_parsing(raw: str, expected: Decimal | None) -> None:
    assert normalize_money(raw).value == expected


def test_money_rounds_half_up_and_preserves_negative_warning() -> None:
    rounded = normalize_money("1.235", decimal_separator=".")
    assert rounded.value == Decimal("1.24")
    assert rounded.issues[0].code is IssueCode.NUMBER_ROUNDED

    negative = normalize_money("(20.00)")
    assert negative.value == Decimal("-20.00")
    assert negative.issues[0].code is IssueCode.NEGATIVE_AMOUNT


def test_invalid_money_is_an_error_not_zero() -> None:
    result = normalize_money("not money")
    assert result.value is None
    assert result.issues[0].code is IssueCode.INVALID_NUMBER
    assert result.issues[0].severity is IssueSeverity.ERROR

    overflow = normalize_money("1000000000000.00")
    assert overflow.value is None
    assert overflow.issues[0].code is IssueCode.INVALID_NUMBER


def test_batch_date_order_is_never_guessed_per_row() -> None:
    assert infer_date_order(["03/04/2026", "31/05/2026"]) is DateOrder.DMY
    assert infer_date_order(["03/04/2026", "05/31/2026"]) is DateOrder.MDY
    assert infer_date_order(["03/04/2026", "04/05/2026"]) is DateOrder.AMBIGUOUS

    ambiguous = normalize_date("03/04/2026", today=date(2026, 9, 19))
    assert ambiguous.value is None
    assert ambiguous.issues[0].code is IssueCode.AMBIGUOUS_DATE_FORMAT
    assert normalize_date("03/04/2026", order=DateOrder.DMY, today=date(2026, 9, 19)).value == date(
        2026, 4, 3
    )


def test_dates_support_explicit_and_iso_formats_and_range_checks() -> None:
    assert normalize_date("2026-09-18", today=date(2026, 9, 19)).value == date(2026, 9, 18)
    assert normalize_date(
        "18_09_2026", explicit_format="%d_%m_%Y", today=date(2026, 9, 19)
    ).value == date(2026, 9, 18)
    assert normalize_date("1989-12-31", today=date(2026, 9, 19)).issues[0].code is (
        IssueCode.DATE_OUT_OF_RANGE
    )
    assert normalize_date("45678", today=date(2026, 9, 19)).issues[0].code is (
        IssueCode.INVALID_DATE
    )


def test_naive_datetime_uses_organization_timezone_then_utc() -> None:
    result = normalize_datetime("2026-09-18 09:30", organization_timezone="Asia/Manila")
    assert result.value == datetime(2026, 9, 18, 1, 30, tzinfo=UTC)


def test_phone_keeps_raw_when_invalid_and_formats_valid_number() -> None:
    valid = normalize_phone("415 555 2671", default_region="US")
    assert valid.raw == "415 555 2671"
    assert valid.e164 == "+14155552671"
    invalid = normalize_phone("call me maybe", default_region="US")
    assert invalid.raw == "call me maybe"
    assert invalid.e164 is None


def test_identity_rules_are_ordered_tenant_scoped_and_deterministic() -> None:
    external = customer_key(
        ORG_ID,
        SOURCE_ID,
        external_id="C-1",
        phone_e164="+14155552671",
        name="Acme LLC",
        postal_code="94107",
    )
    assert external is not None
    assert external.strategy is IdentityStrategy.EXTERNAL_ID
    repeated = customer_key(
        ORG_ID,
        SOURCE_ID,
        external_id="C-1",
        phone_e164=None,
        name=None,
        postal_code=None,
    )
    other_tenant = customer_key(
        OTHER_ORG_ID,
        SOURCE_ID,
        external_id="C-1",
        phone_e164=None,
        name=None,
        postal_code=None,
    )
    assert repeated == external
    assert other_tenant is not None
    assert other_tenant.digest != external.digest

    fallback = customer_key(
        ORG_ID,
        SOURCE_ID,
        external_id=None,
        phone_e164=None,
        name="Acme LLC",
        postal_code=None,
    )
    assert fallback is not None and fallback.low_confidence is True


def test_equipment_without_identity_is_not_invented() -> None:
    assert (
        equipment_key(
            ORG_ID,
            SOURCE_ID,
            external_id=None,
            serial_number=None,
            location_digest=None,
            manufacturer="Carrier",
            model="24ABC",
            equipment_type="Condenser",
        )
        is None
    )


def test_job_key_uses_normalized_narrative() -> None:
    customer_digest = b"customer"
    first = job_key(
        ORG_ID,
        customer_digest,
        service_date=date(2026, 9, 18),
        summary="  NO COOL  ",
        description=None,
        invoice_number="INV-1",
    )
    second = job_key(
        ORG_ID,
        customer_digest,
        service_date=date(2026, 9, 18),
        summary="no cool",
        description=None,
        invoice_number="inv-1",
    )
    assert first == second


def test_source_record_is_immutable_and_copies_extra_fields() -> None:
    extra = {"Lead Source": "Referral"}
    record = SourceRecord(service_date=date(2026, 9, 18), extra_fields=extra)
    extra["Lead Source"] = "Changed"
    assert record.extra_fields["Lead Source"] == "Referral"
    with pytest.raises(FrozenInstanceError):
        record.customer_name = "Acme"  # type: ignore[misc]
    with pytest.raises(TypeError):
        record.extra_fields["Lead Source"] = "Changed"  # type: ignore[index]
