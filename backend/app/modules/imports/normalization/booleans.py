"""Strict, explainable boolean normalization."""

from __future__ import annotations

from collections.abc import Collection

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.normalization.result import NormalizedValue

TRUE_VALUES = frozenset({"y", "yes", "true", "t", "1", "x", "warranty"})
FALSE_VALUES = frozenset({"n", "no", "false", "f", "0", ""})


def normalize_boolean(
    raw: str | None, *, true_values: Collection[str] | None = None
) -> NormalizedValue[bool]:
    value = "" if raw is None else raw.strip().casefold()
    accepted_true = TRUE_VALUES | {item.strip().casefold() for item in (true_values or ())}
    if value in accepted_true:
        return NormalizedValue(True)
    if value in FALSE_VALUES:
        return NormalizedValue(False)
    return NormalizedValue(
        False,
        (
            ImportIssue(
                code=IssueCode.UNKNOWN_ENUM_VALUE,
                severity=IssueSeverity.WARNING,
                message="Unknown boolean value; false was used.",
                raw_value=raw,
            ),
        ),
    )
