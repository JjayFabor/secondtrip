"""Disk-backed, memory-bounded reader for untrusted CSV objects."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import tempfile
from collections.abc import AsyncIterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.profiling.profiler import (
    HARD_COLUMN_CEILING,
    HARD_FIELD_CEILING,
    HARD_FILE_CEILING,
    HARD_ROW_CEILING,
    StreamingLineCounter,
)


class CsvReadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CsvReaderLimits:
    max_file_bytes: int = HARD_FILE_CEILING
    max_rows: int = HARD_ROW_CEILING
    max_field_bytes: int = 32 * 1024
    max_columns: int = HARD_COLUMN_CEILING

    def __post_init__(self) -> None:
        values = (
            ("max_file_bytes", self.max_file_bytes, HARD_FILE_CEILING),
            ("max_rows", self.max_rows, HARD_ROW_CEILING),
            ("max_field_bytes", self.max_field_bytes, HARD_FIELD_CEILING),
            ("max_columns", self.max_columns, HARD_COLUMN_CEILING),
        )
        for name, value, ceiling in values:
            if not 0 < value <= ceiling:
                raise ValueError(f"{name} must be between 1 and {ceiling}")


@dataclass(frozen=True, slots=True)
class ParsedCsvRow:
    row_number: int
    raw_data: dict[str, str]
    row_hash: bytes
    issues: tuple[ImportIssue, ...]


class StagedCsv:
    """A bounded on-disk copy that can be scanned twice without buffering the file."""

    def __init__(
        self,
        handle: BinaryIO,
        *,
        encoding: str,
        delimiter: str,
        has_header: bool,
        columns: tuple[str, ...],
        limits: CsvReaderLimits,
        file_size_bytes: int,
    ) -> None:
        self._handle = handle
        self._encoding = encoding
        self._delimiter = delimiter
        self._has_header = has_header
        self._columns = columns
        self._limits = limits
        self.file_size_bytes = file_size_bytes

    @classmethod
    async def create(
        cls,
        chunks: AsyncIterable[bytes],
        *,
        encoding: str,
        delimiter: str,
        has_header: bool,
        columns: tuple[str, ...],
        limits: CsvReaderLimits,
    ) -> StagedCsv:
        if len(columns) > limits.max_columns:
            raise CsvReadError("TOO_MANY_COLUMNS", "The CSV exceeds the column limit.")
        # Ownership transfers to StagedCsv and close() releases it.
        handle = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115
        total = 0
        prefix = bytearray()
        line_counter = StreamingLineCounter()
        try:
            async for chunk in chunks:
                if not isinstance(chunk, bytes):
                    raise TypeError("CSV chunks must be bytes")
                total += len(chunk)
                if total > limits.max_file_bytes:
                    raise CsvReadError(
                        "FILE_TOO_LARGE", "The CSV exceeds the configured file-size limit."
                    )
                if len(prefix) < 4:
                    prefix.extend(chunk[: 4 - len(prefix)])
                line_counter.feed(chunk)
                header_rows = 1 if has_header else 0
                if line_counter.line_count > limits.max_rows + header_rows:
                    raise CsvReadError("TOO_MANY_ROWS", "The CSV exceeds the configured row limit.")
                if b"\x00" in chunk and not encoding.lower().startswith("utf-16"):
                    raise CsvReadError("NULL_BYTE", "The CSV contains a null byte.")
                await asyncio.to_thread(handle.write, chunk)
            if total == 0:
                raise CsvReadError("EMPTY_FILE", "The uploaded CSV is empty.")
            if bytes(prefix).startswith(b"PK\x03\x04"):
                raise CsvReadError("EXCEL_WORKBOOK", "Export the Excel workbook as CSV first.")
            if bytes(prefix).startswith(b"\x1f\x8b"):
                raise CsvReadError("COMPRESSED_FILE", "Compressed uploads are not supported.")
            await asyncio.to_thread(handle.flush)
            return cls(
                handle,
                encoding=encoding,
                delimiter=delimiter,
                has_header=has_header,
                columns=columns,
                limits=limits,
                file_size_bytes=total,
            )
        except BaseException:
            handle.close()
            raise

    def close(self) -> None:
        self._handle.close()

    def rows(self) -> Iterator[ParsedCsvRow]:
        self._handle.seek(0)
        text = io.TextIOWrapper(
            self._handle,
            encoding=self._encoding,
            errors="replace",
            newline="",
        )
        try:
            reader = csv.reader(text, delimiter=self._delimiter, strict=True)
            if self._has_header:
                try:
                    next(reader)
                except StopIteration:
                    return
            first_row_number = 2 if self._has_header else 1
            for index, values in enumerate(reader):
                if index >= self._limits.max_rows:
                    raise CsvReadError("TOO_MANY_ROWS", "The CSV exceeds the configured row limit.")
                yield self._parse_row(first_row_number + index, values)
        except csv.Error as exc:
            code = "FIELD_TOO_LONG" if "field larger" in str(exc) else "MALFORMED_CSV"
            raise CsvReadError(code, f"The CSV could not be parsed: {exc}") from exc
        finally:
            text.detach()

    def sample_column(self, column: str, *, limit: int = 200) -> list[str]:
        values: list[str] = []
        for row in self.rows():
            value = row.raw_data.get(column, "")
            if value.strip():
                values.append(value)
                if len(values) >= limit:
                    break
        return values

    def _parse_row(self, row_number: int, values: list[str]) -> ParsedCsvRow:
        expected = len(self._columns)
        issues: list[ImportIssue] = []
        if len(values) > expected:
            issues.append(
                ImportIssue(
                    code=IssueCode.TOO_MANY_COLUMNS,
                    severity=IssueSeverity.ERROR,
                    message=f"Row has {len(values)} fields; expected {expected}.",
                )
            )
        elif len(values) < expected:
            issues.append(
                ImportIssue(
                    code=IssueCode.TOO_FEW_COLUMNS,
                    severity=IssueSeverity.ERROR,
                    message=f"Row has {len(values)} fields; expected {expected}.",
                )
            )

        raw_data = {
            name: values[index] if index < len(values) else ""
            for index, name in enumerate(self._columns)
        }
        for index, value in enumerate(values[expected:], start=1):
            raw_data[f"__extra_{index}"] = value

        for field, value in raw_data.items():
            if "\ufffd" in value:
                issues.append(
                    ImportIssue(
                        code=IssueCode.ENCODING_REPLACEMENT,
                        severity=IssueSeverity.WARNING,
                        message="Undecodable bytes were replaced.",
                        field=field,
                        raw_value=value,
                    )
                )
            if len(value.encode("utf-8")) > self._limits.max_field_bytes:
                issues.append(
                    ImportIssue(
                        code=IssueCode.FIELD_TOO_LONG,
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"Field exceeded {self._limits.max_field_bytes} bytes and will be "
                            "truncated when imported."
                        ),
                        field=field,
                        raw_value=value,
                    )
                )

        canonical = json.dumps(
            raw_data, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return ParsedCsvRow(row_number, raw_data, hashlib.sha256(canonical).digest(), tuple(issues))


def temporary_path(handle: BinaryIO) -> Path | None:
    """Exposed only for diagnostics; anonymous temp files normally have no path."""
    name = getattr(handle, "name", None)
    return Path(name) if isinstance(name, str) else None
