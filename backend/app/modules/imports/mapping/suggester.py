"""Deterministic synonym and fuzzy mapping suggestions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from app.modules.imports.mapping.catalogue import TARGET_FIELDS, TargetType
from app.modules.imports.mapping.synonyms import SYNONYMS
from app.modules.imports.profiling.profiler import ColumnProfile, InferredType

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
FUZZY_THRESHOLD = 0.82


class SuggestionStrategy(StrEnum):
    SYNONYM = "synonym"
    FUZZY = "fuzzy"


@dataclass(frozen=True, slots=True)
class MappingSuggestion:
    target_field: str
    source_column: str
    confidence: float
    strategy: SuggestionStrategy


def normalize_header(value: str) -> str:
    return " ".join(part for part in _NON_ALNUM.sub(" ", value.casefold()).split() if part)


def mapping_signature(headers: list[str] | tuple[str, ...]) -> str:
    canonical = "\x1f".join(sorted(header.strip().casefold() for header in headers))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _type_compatible(target_type: TargetType, inferred: InferredType) -> bool:
    if target_type is TargetType.TEXT:
        return True
    compatible = {
        TargetType.DATE: {InferredType.DATE, InferredType.DATETIME},
        TargetType.DATETIME: {InferredType.DATE, InferredType.DATETIME},
        TargetType.MONEY: {InferredType.INTEGER, InferredType.MONEY},
        TargetType.INTEGER: {InferredType.INTEGER},
        TargetType.BOOLEAN: {InferredType.BOOLEAN},
    }
    return inferred in compatible[target_type]


def suggest_mappings(columns: tuple[ColumnProfile, ...]) -> tuple[MappingSuggestion, ...]:
    suggestions: list[MappingSuggestion] = []
    claimed_targets: set[str] = set()
    for column in columns:
        normalized = normalize_header(column.name)
        exact: str | None = None
        for target, aliases in SYNONYMS.items():
            normalized_aliases = {normalize_header(alias) for alias in aliases | {target}}
            if normalized in normalized_aliases:
                exact = target
                break
        if exact and exact not in claimed_targets:
            suggestions.append(
                MappingSuggestion(exact, column.name, 1.0, SuggestionStrategy.SYNONYM)
            )
            claimed_targets.add(exact)
            continue

        candidate: tuple[float, str] | None = None
        for target, aliases in SYNONYMS.items():
            if target in claimed_targets or not _type_compatible(
                TARGET_FIELDS[target].data_type, column.inferred_type
            ):
                continue
            score = max(
                SequenceMatcher(None, normalized, normalize_header(alias)).ratio()
                for alias in aliases | {target}
            )
            if score >= FUZZY_THRESHOLD and (candidate is None or score > candidate[0]):
                candidate = (score, target)
        if candidate:
            score, target = candidate
            suggestions.append(
                MappingSuggestion(target, column.name, score, SuggestionStrategy.FUZZY)
            )
            claimed_targets.add(target)
    return tuple(suggestions)
