"""Memory-bounded profiler for untrusted CSV objects."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import islice

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.profiling.dialect import detect_dialect
from app.modules.imports.profiling.encoding import decode_sample

PROFILE_SAMPLE_BYTES = 1024 * 1024
PROFILE_ROW_SAMPLES = 20
PROFILE_VALUE_SAMPLES = 5
HARD_FILE_CEILING = 500 * 1024 * 1024
HARD_ROW_CEILING = 2_000_000
HARD_FIELD_CEILING = 64 * 1024
HARD_COLUMN_CEILING = 200
csv.field_size_limit(HARD_FIELD_CEILING)


class InferredType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    MONEY = "money"
    DATE = "date"
    DATETIME = "datetime"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class ProfileLimits:
    max_file_bytes: int = HARD_FILE_CEILING
    max_rows: int = HARD_ROW_CEILING
    max_field_bytes: int = 32 * 1024
    max_columns: int = HARD_COLUMN_CEILING

    def __post_init__(self) -> None:
        limits = (
            ("max_file_bytes", self.max_file_bytes, HARD_FILE_CEILING),
            ("max_rows", self.max_rows, HARD_ROW_CEILING),
            ("max_field_bytes", self.max_field_bytes, HARD_FIELD_CEILING),
            ("max_columns", self.max_columns, HARD_COLUMN_CEILING),
        )
        for name, value, ceiling in limits:
            if not 0 < value <= ceiling:
                raise ValueError(f"{name} must be between 1 and {ceiling}")


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    ordinal: int
    sample_values: tuple[str, ...]
    inferred_type: InferredType


@dataclass(frozen=True, slots=True)
class CsvProfile:
    encoding: str
    delimiter: str
    has_header: bool
    columns: tuple[ColumnProfile, ...]
    sample_rows: tuple[dict[str, str], ...]
    approximate_row_count: int
    file_size_bytes: int
    issues: tuple[ImportIssue, ...]


class ProfilingError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class StreamingLineCounter:
    """Count CR, LF, and CRLF lines across arbitrary byte chunk boundaries."""

    def __init__(self) -> None:
        self._mode: str | None = None
        self._undecided = bytearray()
        self._incomplete = b""
        self._pending_cr = False
        self._has_content = False
        self.breaks = 0

    def feed(self, chunk: bytes) -> None:
        if self._mode is None:
            self._undecided.extend(chunk)
            if len(self._undecided) < 2:
                return
            prefix = bytes(self._undecided[:2])
            self._mode = (
                "utf-16-le"
                if prefix == b"\xff\xfe"
                else "utf-16-be"
                if prefix == b"\xfe\xff"
                else "bytes"
            )
            chunk = bytes(self._undecided)
            self._undecided.clear()
        self._feed_decided(chunk)

    def _feed_decided(self, chunk: bytes) -> None:
        units: Iterable[int]
        if self._mode == "bytes":
            units = chunk
        else:
            payload = self._incomplete + chunk
            complete_length = len(payload) - len(payload) % 2
            complete, self._incomplete = payload[:complete_length], payload[complete_length:]
            if self._mode == "utf-16-le":
                units = [
                    int.from_bytes(complete[index : index + 2], "little")
                    for index in range(0, len(complete), 2)
                ]
            else:
                units = [
                    int.from_bytes(complete[index : index + 2], "big")
                    for index in range(0, len(complete), 2)
                ]
        for unit in units:
            self._feed_unit(unit)

    def _feed_unit(self, unit: int) -> None:
        if self._pending_cr:
            if unit == 10:
                self.breaks += 1
                self._pending_cr = False
                self._has_content = False
                return
            self.breaks += 1
            self._pending_cr = False
            self._has_content = False
        if unit == 13:
            self._pending_cr = True
        elif unit == 10:
            self.breaks += 1
            self._has_content = False
        else:
            self._has_content = True

    @property
    def line_count(self) -> int:
        return self.breaks + (1 if self._pending_cr or self._has_content else 0)


_INT = re.compile(r"^[+-]?\d+$")
_MONEY = re.compile(r"^[+-]?(?:[$€£¥]\s*)?\(?\d[\d,.]*\)?$")
_DATE = re.compile(r"^(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})$")
_DATETIME = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}[T ]\d{1,2}:\d{2}")
_TRUE_FALSE = frozenset(
    {"y", "yes", "true", "t", "1", "x", "warranty", "n", "no", "false", "f", "0"}
)


def _infer(values: list[str]) -> InferredType:
    present = [value.strip() for value in values if value.strip()]
    if not present:
        return InferredType.TEXT
    folded = [value.casefold() for value in present]
    if all(value in _TRUE_FALSE for value in folded):
        return InferredType.BOOLEAN
    if all(_INT.fullmatch(value) for value in present):
        return InferredType.INTEGER
    if all(_DATETIME.match(value) for value in present):
        return InferredType.DATETIME
    if all(_DATE.fullmatch(value) for value in present):
        return InferredType.DATE
    if all(_MONEY.fullmatch(value) for value in present):
        return InferredType.MONEY
    return InferredType.TEXT


def _unique_headers(values: list[str]) -> list[str]:
    result: list[str] = []
    counts: dict[str, int] = {}
    for ordinal, raw in enumerate(values):
        base = raw.strip() or f"column_{ordinal + 1}"
        counts[base] = counts.get(base, 0) + 1
        count = counts[base]
        result.append(base if count == 1 else f"{base}_{count}")
    return result


def _parse_rows(text: str, delimiter: str, *, truncated: bool) -> list[list[str]]:
    try:
        reader = csv.reader(
            io.StringIO(text, newline=""), delimiter=delimiter, strict=not truncated
        )
        return list(islice(reader, PROFILE_ROW_SAMPLES + 1))
    except (csv.Error, UnicodeError) as exc:
        if "field larger than field limit" in str(exc):
            raise ProfilingError(
                "FIELD_TOO_LONG", "A sampled field exceeds the hard limit."
            ) from exc
        raise ProfilingError("MALFORMED_CSV", f"The CSV sample could not be parsed: {exc}") from exc


async def profile_csv(
    chunks: AsyncIterable[bytes], limits: ProfileLimits | None = None
) -> CsvProfile:
    """Profile a byte stream while retaining no more than the first 1 MiB."""
    applied = limits or ProfileLimits()
    sample = bytearray()
    total_bytes = 0
    line_counter = StreamingLineCounter()

    async for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise TypeError("CSV chunks must be bytes")
        total_bytes += len(chunk)
        if total_bytes > applied.max_file_bytes:
            raise ProfilingError(
                "FILE_TOO_LARGE", "The CSV exceeds the configured file-size limit."
            )
        line_counter.feed(chunk)
        remaining = PROFILE_SAMPLE_BYTES - len(sample)
        if remaining > 0:
            sample.extend(chunk[:remaining])
        if line_counter.line_count > applied.max_rows + 1:
            raise ProfilingError("TOO_MANY_ROWS", "The CSV exceeds the configured row limit.")

    if total_bytes == 0:
        raise ProfilingError("EMPTY_FILE", "The uploaded CSV is empty.")
    raw_sample = bytes(sample)
    if raw_sample.startswith(b"PK\x03\x04"):
        raise ProfilingError(
            "EXCEL_WORKBOOK",
            "This is an Excel workbook; export it as CSV before uploading.",
        )
    if raw_sample.startswith(b"\x1f\x8b"):
        raise ProfilingError("COMPRESSED_FILE", "Compressed uploads are not supported.")

    decoded = decode_sample(raw_sample)
    if not decoded.text.strip("\ufeff\r\n\t "):
        raise ProfilingError("EMPTY_FILE", "The uploaded CSV contains no data.")
    if "\x00" in decoded.text:
        raise ProfilingError("NULL_BYTE", "The CSV contains a null byte.")

    dialect = detect_dialect(decoded.text)
    rows = _parse_rows(
        decoded.text,
        dialect.delimiter,
        truncated=total_bytes > len(raw_sample),
    )
    rows = [row for row in rows if row]
    if not rows:
        raise ProfilingError("EMPTY_FILE", "The uploaded CSV contains no rows.")

    width = len(rows[0])
    if width > applied.max_columns:
        raise ProfilingError("TOO_MANY_COLUMNS", "The CSV exceeds the configured column limit.")
    if width == 0:
        raise ProfilingError("EMPTY_FILE", "The uploaded CSV contains no columns.")
    for row in rows[: PROFILE_ROW_SAMPLES + 1]:
        for field in row:
            if len(field.encode("utf-8")) > applied.max_field_bytes:
                raise ProfilingError("FIELD_TOO_LONG", "A sampled field exceeds the field limit.")

    if dialect.has_header:
        headers = _unique_headers(rows[0])
        data_rows = rows[1 : PROFILE_ROW_SAMPLES + 1]
    else:
        headers = [f"column_{index + 1}" for index in range(width)]
        data_rows = rows[:PROFILE_ROW_SAMPLES]

    issues = list(decoded.issues)
    if dialect.delimiter_uncertain:
        issues.append(
            ImportIssue(
                code=IssueCode.DELIMITER_UNCERTAIN,
                severity=IssueSeverity.WARNING,
                message="Delimiter detection was ambiguous; comma was used.",
            )
        )
    sample_rows: list[dict[str, str]] = []
    column_values: list[list[str]] = [[] for _ in headers]
    for row_number, row in enumerate(data_rows, start=2 if dialect.has_header else 1):
        if len(row) != width:
            code = IssueCode.TOO_MANY_COLUMNS if len(row) > width else IssueCode.TOO_FEW_COLUMNS
            issues.append(
                ImportIssue(
                    code=code,
                    severity=IssueSeverity.ERROR,
                    message=f"Row {row_number} has {len(row)} fields; expected {width}.",
                )
            )
        normalized_row = (row + [""] * width)[:width]
        sample_rows.append(dict(zip(headers, normalized_row, strict=True)))
        for index, value in enumerate(normalized_row):
            if value and len(column_values[index]) < PROFILE_VALUE_SAMPLES:
                column_values[index].append(value)

    columns = tuple(
        ColumnProfile(
            name=name,
            ordinal=index,
            sample_values=tuple(column_values[index]),
            inferred_type=_infer(column_values[index]),
        )
        for index, name in enumerate(headers)
    )
    approximate_rows = line_counter.line_count
    if dialect.has_header:
        approximate_rows = max(0, approximate_rows - 1)
    return CsvProfile(
        encoding=decoded.encoding,
        delimiter=dialect.delimiter,
        has_header=dialect.has_header,
        columns=columns,
        sample_rows=tuple(sample_rows),
        approximate_row_count=approximate_rows,
        file_size_bytes=total_bytes,
        issues=tuple(issues),
    )
