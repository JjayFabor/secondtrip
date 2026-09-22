"""Explicit, batch-disambiguated date and datetime normalization."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.normalization.result import NormalizedValue

_SLASH_DATE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})(?:\s|$)")


class DateOrder(StrEnum):
    DMY = "dmy"
    MDY = "mdy"
    AMBIGUOUS = "ambiguous"


def infer_date_order(values: list[str] | tuple[str, ...]) -> DateOrder:
    saw_dmy = False
    saw_mdy = False
    scanned = 0
    for value in values:
        if not value.strip():
            continue
        scanned += 1
        if scanned > 200:
            break
        match = _SLASH_DATE.match(value.strip())
        if not match:
            continue
        first, second = int(match.group(1)), int(match.group(2))
        saw_dmy = saw_dmy or first > 12
        saw_mdy = saw_mdy or second > 12
    if saw_dmy and not saw_mdy:
        return DateOrder.DMY
    if saw_mdy and not saw_dmy:
        return DateOrder.MDY
    return DateOrder.AMBIGUOUS


def _parse(raw: str, explicit_format: str | None, order: DateOrder) -> datetime:
    if explicit_format:
        return datetime.strptime(raw, explicit_format)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    formats = (
        ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"]
        if order is DateOrder.DMY
        else [
            "%m/%d/%Y",
            "%m-%d-%Y",
            "%m.%d.%Y",
        ]
    )
    formats.extend(["%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"])
    for date_format in formats:
        try:
            return datetime.strptime(raw, date_format)
        except ValueError:
            continue
    raise ValueError("unparseable date")


def _failure(code: IssueCode, raw: str | None, message: str) -> NormalizedValue[date | None]:
    return NormalizedValue(
        None,
        (ImportIssue(code=code, severity=IssueSeverity.ERROR, message=message, raw_value=raw),),
    )


def normalize_date(
    raw: str | None,
    *,
    explicit_format: str | None = None,
    order: DateOrder = DateOrder.AMBIGUOUS,
    today: date | None = None,
) -> NormalizedValue[date | None]:
    if raw is None or not raw.strip():
        return _failure(IssueCode.MISSING_REQUIRED_FIELD, raw, "A service date is required.")
    value = raw.strip()
    if explicit_format is None and _SLASH_DATE.match(value) and order is DateOrder.AMBIGUOUS:
        return _failure(
            IssueCode.AMBIGUOUS_DATE_FORMAT,
            raw,
            "Date order is ambiguous; choose DD/MM or MM/DD.",
        )
    try:
        parsed = _parse(value, explicit_format, order).date()
    except ValueError:
        return _failure(IssueCode.INVALID_DATE, raw, "Date could not be parsed.")
    reference = today or datetime.now(UTC).date()
    if parsed < date(1990, 1, 1) or parsed > reference + timedelta(days=366):
        return _failure(IssueCode.DATE_OUT_OF_RANGE, raw, "Date is outside the accepted range.")
    return NormalizedValue(parsed)


def normalize_datetime(
    raw: str | None,
    *,
    organization_timezone: str,
    explicit_format: str | None = None,
    order: DateOrder = DateOrder.AMBIGUOUS,
) -> NormalizedValue[datetime | None]:
    if raw is None or not raw.strip():
        return NormalizedValue(None)
    value = raw.strip()
    if explicit_format is None and _SLASH_DATE.match(value) and order is DateOrder.AMBIGUOUS:
        failure = _failure(
            IssueCode.AMBIGUOUS_DATE_FORMAT,
            raw,
            "Date order is ambiguous; choose DD/MM or MM/DD.",
        )
        return NormalizedValue(None, failure.issues)
    try:
        parsed = _parse(value, explicit_format, order)
        timezone = ZoneInfo(organization_timezone)
    except (ValueError, ZoneInfoNotFoundError):
        failure = _failure(IssueCode.INVALID_DATE, raw, "Datetime or timezone could not be parsed.")
        return NormalizedValue(None, failure.issues)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return NormalizedValue(parsed.astimezone(UTC))
