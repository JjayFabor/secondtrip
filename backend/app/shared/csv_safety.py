"""Spreadsheet-safe rendering for every CSV export."""

from __future__ import annotations

import json
from typing import Any, Final

_FORMULA_PREFIXES: Final = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> str:
    """Render a cell without allowing spreadsheet formula execution."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value, separators=(",", ":"), sort_keys=True)
    else:
        rendered = str(value)
    if rendered.startswith(_FORMULA_PREFIXES):
        return "'" + rendered
    return rendered
