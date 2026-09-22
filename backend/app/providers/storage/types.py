"""Application-owned storage value objects; vendor SDK types never cross this boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int
    content_type: str
    etag: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    key: str
    size_bytes: int
    content_type: str
    etag: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PresignedUpload:
    url: str
    method: str
    key: str
    max_bytes: int
    expires_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
    fields: dict[str, str] = field(default_factory=dict)
