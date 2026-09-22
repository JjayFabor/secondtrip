"""Server-owned object-key construction and download-filename hygiene."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from uuid import UUID

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def import_source_key(organization_id: UUID, import_batch_id: UUID) -> str:
    return f"orgs/{organization_id}/imports/{import_batch_id}/source.csv"


def import_error_key(organization_id: UUID, import_batch_id: UUID) -> str:
    return f"orgs/{organization_id}/imports/{import_batch_id}/errors.csv"


def validate_storage_key(key: str) -> str:
    path = PurePosixPath(key)
    raw_parts = key.split("/")
    if (
        not key
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise ValueError("Invalid storage key.")
    return path.as_posix()


def validate_storage_prefix(prefix: str) -> str:
    """Normalize a list/delete prefix while preserving its directory boundary."""
    return validate_storage_key(prefix.rstrip("/")) + "/"


def safe_download_filename(filename: str | None, *, fallback: str = "download.csv") -> str:
    if filename is None:
        return fallback
    cleaned = _CONTROL_CHARACTERS.sub("", filename.replace("/", "_").replace("\\", "_"))
    cleaned = cleaned.lstrip(".").strip()[:200]
    return cleaned or fallback
