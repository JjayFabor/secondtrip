"""Locale-aware Decimal money normalization without float conversion."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.normalization.result import NormalizedValue

_EMPTY = frozenset({"", "-", "n/a", "na", "null"})
_CURRENCY = re.compile(r"[^\d,.'() +\-]")
_MAX_NUMERIC_14_2 = Decimal("999999999999.99")


def _infer_separators(value: str) -> tuple[str | None, str | None]:
    comma = value.rfind(",")
    dot = value.rfind(".")
    if comma >= 0 and dot >= 0:
        decimal = "," if comma > dot else "."
        return decimal, "." if decimal == "," else ","
    separator = "," if comma >= 0 else "." if dot >= 0 else None
    if separator is None:
        return None, None
    if value.count(separator) == 1 and len(value) - value.rfind(separator) - 1 == 2:
        return separator, None
    return None, separator


def normalize_money(
    raw: str | None,
    *,
    decimal_separator: str | None = None,
    thousands_separator: str | None = None,
) -> NormalizedValue[Decimal | None]:
    if raw is None or raw.strip().casefold() in _EMPTY:
        return NormalizedValue(None)
    cleaned = _CURRENCY.sub("", raw).replace(" ", "").replace("'", "")
    negative_parentheses = cleaned.startswith("(") and cleaned.endswith(")")
    if negative_parentheses:
        cleaned = cleaned[1:-1]
    inferred_decimal, inferred_thousands = _infer_separators(cleaned)
    decimal_separator = decimal_separator or inferred_decimal
    if thousands_separator is None and inferred_thousands != decimal_separator:
        thousands_separator = inferred_thousands
    if thousands_separator:
        cleaned = cleaned.replace(thousands_separator, "")
    if decimal_separator and decimal_separator != ".":
        cleaned = cleaned.replace(decimal_separator, ".")
    if negative_parentheses:
        cleaned = "-" + cleaned
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return NormalizedValue(
            None,
            (
                ImportIssue(
                    code=IssueCode.INVALID_NUMBER,
                    severity=IssueSeverity.ERROR,
                    message="Amount could not be parsed.",
                    raw_value=raw,
                ),
            ),
        )

    issues: list[ImportIssue] = []
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded != amount:
        amount = rounded
        issues.append(
            ImportIssue(
                code=IssueCode.NUMBER_ROUNDED,
                severity=IssueSeverity.WARNING,
                message="Amount had more than two decimal places and was rounded half-up.",
                raw_value=raw,
            )
        )
    if amount < 0:
        issues.append(
            ImportIssue(
                code=IssueCode.NEGATIVE_AMOUNT,
                severity=IssueSeverity.WARNING,
                message="Negative amount was retained.",
                raw_value=raw,
            )
        )
    if abs(amount) > _MAX_NUMERIC_14_2:
        return NormalizedValue(
            None,
            (
                ImportIssue(
                    code=IssueCode.INVALID_NUMBER,
                    severity=IssueSeverity.ERROR,
                    message="Amount exceeds the numeric(14,2) storage range.",
                    raw_value=raw,
                ),
            ),
        )
    return NormalizedValue(amount, tuple(issues))
