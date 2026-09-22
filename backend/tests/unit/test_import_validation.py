from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest

from app.modules.imports.issues import IssueCode
from app.modules.imports.mapping.document import MappingDocument
from app.modules.imports.models import ImportRow, ImportRowStatus
from app.modules.imports.normalization.dates import DateOrder
from app.modules.imports.processing.reader import CsvReaderLimits, CsvReadError, StagedCsv
from app.modules.imports.processing.validator import validate_row
from app.modules.imports.reporting.error_report import build_error_report


async def chunks(*values: bytes) -> AsyncIterator[bytes]:
    for value in values:
        yield value


async def test_staged_reader_preserves_rows_and_reports_shape_errors() -> None:
    document = await StagedCsv.create(
        chunks(b"Customer,Date\r\nAcme,2026-09-18\r\n", b"Beta\r\n"),
        encoding="utf-8",
        delimiter=",",
        has_header=True,
        columns=("Customer", "Date"),
        limits=CsvReaderLimits(),
    )
    try:
        rows = list(document.rows())
        assert [row.row_number for row in rows] == [2, 3]
        assert rows[0].raw_data == {"Customer": "Acme", "Date": "2026-09-18"}
        assert rows[1].raw_data == {"Customer": "Beta", "Date": ""}
        assert [issue.code for issue in rows[1].issues] == [IssueCode.TOO_FEW_COLUMNS]
        assert document.sample_column("Date") == ["2026-09-18"]
    finally:
        document.close()


async def test_staged_reader_aborts_at_streaming_file_limit() -> None:
    with pytest.raises(CsvReadError) as caught:
        await StagedCsv.create(
            chunks(b"a,b\n", b"1,2\n"),
            encoding="utf-8",
            delimiter=",",
            has_header=True,
            columns=("a", "b"),
            limits=CsvReaderLimits(max_file_bytes=5),
        )
    assert caught.value.code == "FILE_TOO_LARGE"


async def test_staged_reader_aborts_at_streaming_row_limit() -> None:
    with pytest.raises(CsvReadError) as caught:
        await StagedCsv.create(
            chunks(b"a\n1\n2\n"),
            encoding="utf-8",
            delimiter=",",
            has_header=True,
            columns=("a",),
            limits=CsvReaderLimits(max_rows=1),
        )
    assert caught.value.code == "TOO_MANY_ROWS"


async def test_validator_never_guesses_ambiguous_dates() -> None:
    document = await StagedCsv.create(
        chunks(b"Customer,Date\nAcme,03/04/2026\n"),
        encoding="utf-8",
        delimiter=",",
        has_header=True,
        columns=("Customer", "Date"),
        limits=CsvReaderLimits(),
    )
    mapping = MappingDocument.model_validate(
        {
            "version": 1,
            "fields": {
                "service_date": {"source_column": "Date"},
                "customer_name": {"source_column": "Customer"},
            },
        }
    )
    try:
        result = validate_row(
            next(document.rows()),
            mapping,
            organization_id=uuid4(),
            source_system_id=uuid4(),
            organization_timezone="America/Chicago",
            date_order=DateOrder.AMBIGUOUS,
            max_field_bytes=32 * 1024,
        )
    finally:
        document.close()
    assert result.status is ImportRowStatus.ERROR
    assert IssueCode.AMBIGUOUS_DATE_FORMAT in {issue.code for issue in result.issues}
    assert result.source_record is None


def test_error_report_escapes_every_attacker_controlled_cell() -> None:
    row = ImportRow(
        organization_id=uuid4(),
        import_batch_id=uuid4(),
        row_number=2,
        raw_data={"Revenue": "=2+2"},
        row_hash=b"hash",
        status=ImportRowStatus.ERROR,
        issues=[
            {
                "code": "INVALID_NUMBER",
                "severity": "error",
                "field": "=field",
                "message": "+message",
                "raw_value": "@payload",
            }
        ],
    )
    report = build_error_report([row])
    try:
        rendered = report.read().decode()
    finally:
        report.close()
    assert "'=field" in rendered
    assert "'+message" in rendered
    assert "'@payload" in rendered
