"""Private filesystem storage with HMAC-signed local development URLs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.providers.storage.keys import (
    safe_download_filename,
    validate_storage_key,
    validate_storage_prefix,
)
from app.providers.storage.types import ObjectMetadata, PresignedUpload, StoredObject


class InvalidStorageToken(ValueError):
    pass


class LocalStorageProvider:
    def __init__(self, *, root: Path, app_secret: str, base_url: str) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._secret = app_secret.encode("utf-8")
        self._base_url = base_url.rstrip("/")
        self._content_types: dict[str, str] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    def _path(self, key: str) -> Path:
        key = validate_storage_key(key)
        path = (self._root / key).resolve()
        if not path.is_relative_to(self._root):
            raise ValueError("Storage key escaped its root.")
        return path

    async def upload(
        self,
        key: str,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        key = validate_storage_key(key)
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=path.parent) as temporary:
                temporary_path = Path(temporary.name)
                if isinstance(data, bytes):
                    digest.update(data)
                    size = len(data)
                    await asyncio.to_thread(temporary.write, data)
                else:
                    async for chunk in data:
                        digest.update(chunk)
                        size += len(chunk)
                        await asyncio.to_thread(temporary.write, chunk)
                await asyncio.to_thread(temporary.flush)
                await asyncio.to_thread(os.fsync, temporary.fileno())
            await asyncio.to_thread(os.replace, temporary_path, path)
        except BaseException:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

        object_metadata = dict(metadata or {})
        self._content_types[key] = content_type
        self._metadata[key] = object_metadata
        return StoredObject(key, size, content_type, digest.hexdigest(), object_metadata)

    async def download(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            while chunk := await asyncio.to_thread(handle.read, 64 * 1024):
                yield chunk
        finally:
            await asyncio.to_thread(handle.close)

    async def delete(self, key: str) -> None:
        key = validate_storage_key(key)
        await asyncio.to_thread(self._path(key).unlink, missing_ok=True)
        self._content_types.pop(key, None)
        self._metadata.pop(key, None)

    async def delete_prefix(self, prefix: str) -> int:
        prefix = validate_storage_prefix(prefix).rstrip("/")
        root = self._path(prefix)
        if not await asyncio.to_thread(root.exists):
            return 0
        files = await asyncio.to_thread(
            lambda: [path for path in root.rglob("*") if path.is_file()]
        )
        for path in files:
            await asyncio.to_thread(path.unlink, missing_ok=True)
            relative_key = path.relative_to(self._root).as_posix()
            self._content_types.pop(relative_key, None)
            self._metadata.pop(relative_key, None)
        for directory in sorted((path for path in root.rglob("*") if path.is_dir()), reverse=True):
            await asyncio.to_thread(directory.rmdir)
        await asyncio.to_thread(root.rmdir)
        return len(files)

    async def head(self, key: str) -> ObjectMetadata | None:
        key = validate_storage_key(key)
        path = self._path(key)
        if not await asyncio.to_thread(path.is_file):
            return None

        def _digest() -> tuple[int, str]:
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            return size, digest.hexdigest()

        size, etag = await asyncio.to_thread(_digest)
        return ObjectMetadata(
            key=key,
            size_bytes=size,
            content_type=self._content_types.get(key, "application/octet-stream"),
            etag=etag,
            metadata=dict(self._metadata.get(key, {})),
        )

    async def signed_download_url(
        self,
        key: str,
        *,
        expires_in: int = 300,
        download_filename: str | None = None,
    ) -> str:
        key = validate_storage_key(key)
        token = self._sign(
            {
                "op": "download",
                "key": key,
                "exp": int((datetime.now(UTC) + timedelta(seconds=expires_in)).timestamp()),
                "filename": safe_download_filename(download_filename),
            }
        )
        return f"{self._base_url}/api/v1/storage/local/{token}"

    async def signed_upload_url(
        self,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        expires_in: int = 900,
    ) -> PresignedUpload:
        key = validate_storage_key(key)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        token = self._sign(
            {
                "op": "upload",
                "key": key,
                "exp": int(expires_at.timestamp()),
                "content_type": content_type,
                "max_bytes": max_bytes,
            }
        )
        return PresignedUpload(
            url=f"{self._base_url}/api/v1/storage/local/{token}",
            method="PUT",
            key=key,
            max_bytes=max_bytes,
            expires_at=expires_at,
            headers={"Content-Type": content_type},
        )

    def verify_token(self, token: str, *, operation: str) -> dict[str, Any]:
        try:
            encoded, signature = token.split(".", maxsplit=1)
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidStorageToken("Invalid storage signature.")
            padded = encoded + "=" * (-len(encoded) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            if payload.get("op") != operation:
                raise InvalidStorageToken("Storage operation mismatch.")
            if int(payload["exp"]) < int(datetime.now(UTC).timestamp()):
                raise InvalidStorageToken("Storage URL expired.")
            validate_storage_key(str(payload["key"]))
            return dict(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, InvalidStorageToken):
                raise
            raise InvalidStorageToken("Invalid storage token.") from exc

    def _sign(self, payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{encoded}.{signature}"
