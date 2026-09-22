"""Vendor-neutral object-storage protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.providers.storage.types import ObjectMetadata, PresignedUpload, StoredObject


class StorageProvider(Protocol):
    async def upload(
        self,
        key: str,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    def download(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...

    async def delete_prefix(self, prefix: str) -> int: ...

    async def head(self, key: str) -> ObjectMetadata | None: ...

    async def signed_download_url(
        self,
        key: str,
        *,
        expires_in: int = 300,
        download_filename: str | None = None,
    ) -> str: ...

    async def signed_upload_url(
        self,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        expires_in: int = 900,
    ) -> PresignedUpload: ...
