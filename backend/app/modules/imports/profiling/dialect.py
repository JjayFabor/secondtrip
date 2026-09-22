"""CSV delimiter and header detection."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass

DELIMITERS = (",", ";", "\t", "|")
_NUMBER = re.compile(r"^[+-]?(?:\d{1,3}(?:[,.]\d{3})+|\d+)(?:[,.]\d+)?$")
_DATE = re.compile(r"^(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})$")


@dataclass(frozen=True, slots=True)
class DialectGuess:
    delimiter: str
    has_header: bool
    delimiter_uncertain: bool


def _looks_typed(value: str) -> bool:
    stripped = value.strip()
    return bool(_NUMBER.fullmatch(stripped) or _DATE.fullmatch(stripped))


def _fallback_delimiter(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines()[:20] if line]
    if not lines:
        return ",", True
    scored: list[tuple[tuple[int, int], str]] = []
    for delimiter in DELIMITERS:
        counts = [line.count(delimiter) for line in lines]
        nonzero = [count for count in counts if count > 0]
        consistency = max((counts.count(value) for value in set(nonzero)), default=0)
        scored.append(((consistency, sum(nonzero)), delimiter))
    scored.sort(reverse=True)
    best_score, best = scored[0]
    tied = sum(score == best_score for score, _ in scored) > 1
    if best_score == (0, 0) or tied:
        return ",", True
    return best, False


def detect_dialect(text: str) -> DialectGuess:
    sniff_sample = text[: 64 * 1024]
    sniffer = csv.Sniffer()
    uncertain = False
    try:
        delimiter = sniffer.sniff(sniff_sample, delimiters="".join(DELIMITERS)).delimiter
    except csv.Error:
        delimiter, uncertain = _fallback_delimiter(text)

    try:
        has_header = sniffer.has_header(sniff_sample)
    except csv.Error:
        has_header = True

    rows = list(csv.reader(text.splitlines()[:6], delimiter=delimiter))
    if len(rows) >= 2 and rows[0]:
        first_is_text = all(not _looks_typed(value) for value in rows[0])
        later_typed = sum(_looks_typed(value) for row in rows[1:] for value in row)
        later_total = sum(len(row) for row in rows[1:])
        if first_is_text and later_total and later_typed * 2 >= later_total:
            has_header = True
    return DialectGuess(delimiter, has_header, uncertain)
