"""Unicode-safe text and identity-name normalization."""

from __future__ import annotations

import re
import unicodedata

from app.modules.imports.issues import ImportIssue, IssueCode, IssueSeverity
from app.modules.imports.normalization.result import NormalizedValue

DEFAULT_MAX_TEXT_BYTES = 32 * 1024
TRUNCATION_MARKER = "… [truncated]"
_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n\t]+")
_NAME_PUNCTUATION = re.compile(r"[^\w\s]", re.UNICODE)
_LEGAL_SUFFIX = re.compile(r"\s+(?:llc|incorporated|inc|limited|ltd|corp(?:oration)?)\.?$", re.I)


def _strip_controls(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in {"\n", "\t"} or not unicodedata.category(character).startswith("C")
    )


def _truncate_utf8(value: str, max_bytes: int) -> str:
    marker = TRUNCATION_MARKER.encode()
    if max_bytes <= len(marker):
        return marker[:max_bytes].decode("utf-8", errors="ignore")
    prefix = value.encode()[: max_bytes - len(marker)].decode("utf-8", errors="ignore")
    return prefix + TRUNCATION_MARKER


def normalize_text(
    raw: str | None, *, max_bytes: int = DEFAULT_MAX_TEXT_BYTES
) -> NormalizedValue[str | None]:
    if raw is None:
        return NormalizedValue(None)
    value = unicodedata.normalize("NFC", _strip_controls(raw))
    value = _HORIZONTAL_WHITESPACE.sub(" ", value).strip()
    if not value:
        return NormalizedValue(None)
    if len(value.encode()) <= max_bytes:
        return NormalizedValue(value)
    truncated = _truncate_utf8(value, max_bytes)
    return NormalizedValue(
        truncated,
        (
            ImportIssue(
                code=IssueCode.FIELD_TOO_LONG,
                severity=IssueSeverity.WARNING,
                message=f"Text exceeded {max_bytes} bytes and was truncated.",
                raw_value=raw,
            ),
        ),
    )


def normalize_name(raw: str | None) -> str | None:
    normalized = normalize_text(raw).value
    if normalized is None:
        return None
    value = _NAME_PUNCTUATION.sub(" ", normalized.casefold())
    value = " ".join(value.split())
    while _LEGAL_SUFFIX.search(value):
        value = _LEGAL_SUFFIX.sub("", value).strip()
    return value or None
