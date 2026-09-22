"""Formula-safe, bounded CSV error report generation."""

from __future__ import annotations

import csv
import io
import tempfile
from typing import BinaryIO

from app.modules.imports.models import ImportRow
from app.shared.csv_safety import csv_safe

REPORT_COLUMNS = ("row_number", "status", "error_code", "field", "message", "raw_value")


class ErrorReportWriter:
    def __init__(self) -> None:
        # Ownership transfers to the caller after finish().
        self.handle = tempfile.TemporaryFile(mode="w+b")  # noqa: SIM115
        self._text = io.TextIOWrapper(self.handle, encoding="utf-8", newline="", write_through=True)
        self._writer = csv.writer(self._text, lineterminator="\r\n")
        self._writer.writerow([csv_safe(value) for value in REPORT_COLUMNS])

    def write_rows(self, rows: list[ImportRow]) -> None:
        for row in rows:
            for issue in row.issues:
                cells = (
                    row.row_number,
                    row.status.value,
                    issue.get("code"),
                    issue.get("field"),
                    issue.get("message"),
                    issue.get("raw_value"),
                )
                self._writer.writerow([csv_safe(value) for value in cells])

    def finish(self) -> BinaryIO:
        self._text.flush()
        self._text.detach()
        self.handle.seek(0)
        return self.handle


def build_error_report(rows: list[ImportRow]) -> BinaryIO:
    writer = ErrorReportWriter()
    writer.write_rows(rows)
    return writer.finish()
