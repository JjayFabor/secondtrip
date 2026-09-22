"""In-memory StorageProvider used by tests."""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from app.providers.storage.keys import validate_storage_key, validate_storage_prefix
from app.providers.storage.types import ObjectMetadata, PresignedUpload, StoredObject


class InMemoryStorageProvider:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str, dict[str, str]]] = {}

    async def upload(
        self,
        key: str,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        key = validate_storage_key(key)
        if isinstance(data, bytes):
            body = data
        else:
            chunks = [chunk async for chunk in data]
            body = b"".join(chunks)
        object_metadata = dict(metadata or {})
        self._objects[key] = (body, content_type, object_metadata)
        etag = hashlib.sha256(body).hexdigest()
        return StoredObject(key, len(body), content_type, etag, object_metadata)

    async def download(self, key: str) -> AsyncIterator[bytes]:
        key = validate_storage_key(key)
        body, _content_type, _metadata = self._objects[key]
        yield body

    async def delete(self, key: str) -> None:
        self._objects.pop(validate_storage_key(key), None)

    async def delete_prefix(self, prefix: str) -> int:
        prefix = validate_storage_prefix(prefix)
        matches = [key for key in self._objects if key.startswith(prefix)]
        for key in matches:
            del self._objects[key]
        return len(matches)

    async def head(self, key: str) -> ObjectMetadata | None:
        key = validate_storage_key(key)
        stored = self._objects.get(key)
        if stored is None:
            return None
        body, content_type, metadata = stored
        return ObjectMetadata(
            key=key,
            size_bytes=len(body),
            content_type=content_type,
            etag=hashlib.sha256(body).hexdigest(),
            metadata=dict(metadata),
        )

    async def signed_download_url(
        self,
        key: str,
        *,
        expires_in: int = 300,
        download_filename: str | None = None,
    ) -> str:
        key = validate_storage_key(key)
        return f"memory://download/{key}"

    async def signed_upload_url(
        self,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        expires_in: int = 900,
    ) -> PresignedUpload:
        key = validate_storage_key(key)
        return PresignedUpload(
            url=f"memory://upload/{key}",
            method="PUT",
            key=key,
            max_bytes=max_bytes,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            headers={"Content-Type": content_type},
        )
