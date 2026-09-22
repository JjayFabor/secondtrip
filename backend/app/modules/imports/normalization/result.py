"""Common normalization result type."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.issues import ImportIssue


@dataclass(frozen=True, slots=True)
class NormalizedValue[T]:
    value: T
    issues: tuple[ImportIssue, ...] = ()
