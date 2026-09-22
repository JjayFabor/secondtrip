"""Stable, transport-neutral import issue types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCode(StrEnum):
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_DATE = "INVALID_DATE"
    AMBIGUOUS_DATE_FORMAT = "AMBIGUOUS_DATE_FORMAT"
    DATE_OUT_OF_RANGE = "DATE_OUT_OF_RANGE"
    UNRESOLVABLE_CUSTOMER = "UNRESOLVABLE_CUSTOMER"
    INVALID_NUMBER = "INVALID_NUMBER"
    NUMBER_ROUNDED = "NUMBER_ROUNDED"
    NEGATIVE_AMOUNT = "NEGATIVE_AMOUNT"
    TOO_MANY_COLUMNS = "TOO_MANY_COLUMNS"
    TOO_FEW_COLUMNS = "TOO_FEW_COLUMNS"
    FIELD_TOO_LONG = "FIELD_TOO_LONG"
    UNKNOWN_ENUM_VALUE = "UNKNOWN_ENUM_VALUE"
    DUPLICATE_ROW_IN_FILE = "DUPLICATE_ROW_IN_FILE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    ENCODING_UNCERTAIN = "ENCODING_UNCERTAIN"
    ENCODING_REPLACEMENT = "ENCODING_REPLACEMENT"
    DELIMITER_UNCERTAIN = "DELIMITER_UNCERTAIN"
    EQUIPMENT_NOT_RESOLVED = "EQUIPMENT_NOT_RESOLVED"
    ROW_SKIPPED_BY_FILTER = "ROW_SKIPPED_BY_FILTER"


@dataclass(frozen=True, slots=True)
class ImportIssue:
    code: IssueCode
    severity: IssueSeverity
    message: str
    field: str | None = None
    raw_value: str | None = None
