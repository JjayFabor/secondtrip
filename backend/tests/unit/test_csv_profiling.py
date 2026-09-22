from __future__ import annotations

import codecs
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.modules.imports.issues import IssueCode
from app.modules.imports.profiling import ProfileLimits, ProfilingError, profile_csv

FIXTURES = Path(__file__).parents[1] / "fixtures" / "csv" / "adversarial"


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


@pytest.mark.asyncio
async def test_profiles_excel_style_utf16_tsv_across_chunks() -> None:
    text = "Customer\tCompleted Date\tInvoice Total\r\nAcme\t09/18/2026\t1,234.56\r\n"
    payload = codecs.BOM_UTF16_LE + text.encode("utf-16-le")

    profile = await profile_csv(chunks(payload[:1], payload[1:17], payload[17:]))

    assert profile.encoding == "utf-16-le"
    assert profile.delimiter == "\t"
    assert profile.has_header is True
    assert [column.name for column in profile.columns] == [
        "Customer",
        "Completed Date",
        "Invoice Total",
    ]
    assert profile.sample_rows[0]["Invoice Total"] == "1,234.56"
    assert profile.approximate_row_count == 1


@pytest.mark.asyncio
async def test_suffixes_duplicate_headers_and_keeps_formula_payloads_raw() -> None:
    duplicate = (FIXTURES / "duplicate_headers.csv").read_bytes()
    profile = await profile_csv(chunks(duplicate))
    assert [column.name for column in profile.columns] == [
        "Customer",
        "Customer_2",
        "Completed Date",
    ]

    formula = await profile_csv(chunks((FIXTURES / "formula_payloads.csv").read_bytes()))
    assert formula.sample_rows[0] == {
        "customer_name": "=2+2",
        "summary": "+SUM(A1:A2)",
        "description": "-1+1",
        "technician_notes": "@malicious",
    }


@pytest.mark.asyncio
async def test_header_only_file_is_valid_with_zero_data_rows() -> None:
    profile = await profile_csv(chunks((FIXTURES / "header_only.csv").read_bytes()))
    assert profile.has_header is True
    assert profile.approximate_row_count == 0
    assert profile.sample_rows == ()


@pytest.mark.asyncio
async def test_handles_mixed_line_endings() -> None:
    payload = b"customer,service date\r\nAcme,2026-09-18\nBeta,2026-09-19\rGamma,2026-09-20\r\n"
    profile = await profile_csv(chunks(payload))
    assert len(profile.sample_rows) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "EMPTY_FILE"),
        (b"PK\x03\x04workbook", "EXCEL_WORKBOOK"),
        (b"\x1f\x8bcompressed", "COMPRESSED_FILE"),
        (b"a,b\nvalue,\x00bad\n", "NULL_BYTE"),
        (b'a,b\n"unterminated,b\n', "MALFORMED_CSV"),
    ],
)
async def test_rejects_adversarial_file_shapes(payload: bytes, code: str) -> None:
    with pytest.raises(ProfilingError) as caught:
        await profile_csv(chunks(payload))
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_streaming_limits_abort_without_buffering_entire_object() -> None:
    with pytest.raises(ProfilingError, match="file-size") as file_error:
        await profile_csv(chunks(b"a,b\n", b"1,2\n"), ProfileLimits(max_file_bytes=5))
    assert file_error.value.code == "FILE_TOO_LARGE"

    with pytest.raises(ProfilingError, match="row limit") as row_error:
        await profile_csv(chunks(b"a\n1\n2\n"), ProfileLimits(max_rows=1))
    assert row_error.value.code == "TOO_MANY_ROWS"

    with pytest.raises(ProfilingError) as cr_only_rows:
        await profile_csv(chunks(b"a\r1\r2\r"), ProfileLimits(max_rows=1))
    assert cr_only_rows.value.code == "TOO_MANY_ROWS"


def test_limits_cannot_exceed_architecture_hard_ceilings() -> None:
    with pytest.raises(ValueError, match="max_field_bytes"):
        ProfileLimits(max_field_bytes=64 * 1024 + 1)
    with pytest.raises(ValueError, match="max_columns"):
        ProfileLimits(max_columns=201)


@pytest.mark.asyncio
async def test_enforces_column_and_field_limits() -> None:
    with pytest.raises(ProfilingError) as columns:
        await profile_csv(chunks(b"a,b,c\n1,2,3\n"), ProfileLimits(max_columns=2))
    assert columns.value.code == "TOO_MANY_COLUMNS"

    with pytest.raises(ProfilingError) as field:
        await profile_csv(chunks(b"a\n12345\n"), ProfileLimits(max_field_bytes=4))
    assert field.value.code == "FIELD_TOO_LONG"


@pytest.mark.asyncio
async def test_reports_ragged_sample_rows() -> None:
    profile = await profile_csv(chunks(b"a,b\n1\n2,3,4\n"))
    assert [issue.code for issue in profile.issues] == [
        IssueCode.TOO_FEW_COLUMNS,
        IssueCode.TOO_MANY_COLUMNS,
    ]
