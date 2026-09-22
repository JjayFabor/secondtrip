"""Cloudflare R2 implementation of the application storage boundary."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from urllib.parse import quote

import aioboto3
from aiobotocore.config import AioConfig
from botocore.exceptions import ClientError

from app.providers.storage.keys import (
    safe_download_filename,
    validate_storage_key,
    validate_storage_prefix,
)
from app.providers.storage.types import ObjectMetadata, PresignedUpload, StoredObject

_CHUNK_BYTES = 64 * 1024
_MAX_PRESIGN_SECONDS = 7 * 24 * 60 * 60


class _S3Client(Protocol):
    async def put_object(self, **kwargs: object) -> dict[str, Any]: ...

    async def upload_fileobj(
        self,
        fileobj: Any,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, object],
    ) -> None: ...

    async def get_object(self, **kwargs: object) -> dict[str, Any]: ...

    async def delete_object(self, **kwargs: object) -> dict[str, Any]: ...

    async def delete_objects(self, **kwargs: object) -> dict[str, Any]: ...

    async def list_objects_v2(self, **kwargs: object) -> dict[str, Any]: ...

    async def head_object(self, **kwargs: object) -> dict[str, Any]: ...

    async def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, object],
        ExpiresIn: int,
    ) -> str: ...


type _ClientFactory = Callable[[], AbstractAsyncContextManager[_S3Client]]


class R2StorageProvider:
    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region: str = "auto",
        client_factory: _ClientFactory | None = None,
    ) -> None:
        self._bucket = bucket
        if client_factory is not None:
            self._client_factory = client_factory
            return

        session = aioboto3.Session()
        config = AioConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"mode": "standard", "max_attempts": 4},
        )

        def build_client() -> AbstractAsyncContextManager[_S3Client]:
            client = session.client(
                "s3",
                endpoint_url=endpoint_url.rstrip("/"),
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name=region,
                config=config,
            )
            return cast(AbstractAsyncContextManager[_S3Client], client)

        self._client_factory = build_client

    async def upload(
        self,
        key: str,
        data: bytes | AsyncIterator[bytes],
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        key = validate_storage_key(key)
        custom_metadata = dict(metadata or {})
        if isinstance(data, bytes):
            async with self._client_factory() as client:
                response = await client.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                    Metadata=custom_metadata,
                )
            return StoredObject(
                key=key,
                size_bytes=len(data),
                content_type=content_type,
                etag=_clean_etag(response.get("ETag")),
                metadata=custom_metadata,
            )

        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as temporary:
            size = 0
            async for chunk in data:
                size += len(chunk)
                await asyncio.to_thread(temporary.write, chunk)
            await asyncio.to_thread(temporary.seek, 0)
            async with self._client_factory() as client:
                await client.upload_fileobj(
                    temporary,
                    self._bucket,
                    key,
                    ExtraArgs={"ContentType": content_type, "Metadata": custom_metadata},
                )
                response = await client.head_object(Bucket=self._bucket, Key=key)
        return StoredObject(
            key=key,
            size_bytes=size,
            content_type=content_type,
            etag=_clean_etag(response.get("ETag")),
            metadata=custom_metadata,
        )

    async def download(self, key: str) -> AsyncIterator[bytes]:
        key = validate_storage_key(key)
        async with self._client_factory() as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            body: Any = response["Body"]
            try:
                while chunk := await body.read(_CHUNK_BYTES):
                    yield bytes(chunk)
            finally:
                body.close()

    async def delete(self, key: str) -> None:
        key = validate_storage_key(key)
        async with self._client_factory() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        prefix = validate_storage_prefix(prefix)
        deleted = 0
        start_after: str | None = None
        async with self._client_factory() as client:
            while True:
                params: dict[str, object] = {
                    "Bucket": self._bucket,
                    "Prefix": prefix,
                    "MaxKeys": 1000,
                }
                if start_after is not None:
                    params["StartAfter"] = start_after
                response = await client.list_objects_v2(**params)
                keys = [
                    str(item["Key"])
                    for item in response.get("Contents", [])
                    if isinstance(item, dict) and item.get("Key") is not None
                ]
                if keys:
                    await client.delete_objects(
                        Bucket=self._bucket,
                        Delete={
                            "Objects": [{"Key": key} for key in keys],
                            "Quiet": True,
                        },
                    )
                    deleted += len(keys)
                if not response.get("IsTruncated"):
                    break
                if not keys:
                    raise RuntimeError(
                        "R2 returned a truncated listing without an object key."
                    )
                start_after = keys[-1]
        return deleted

    async def head(self, key: str) -> ObjectMetadata | None:
        key = validate_storage_key(key)
        try:
            async with self._client_factory() as client:
                response = await client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return ObjectMetadata(
            key=key,
            size_bytes=int(response["ContentLength"]),
            content_type=str(response.get("ContentType", "application/octet-stream")),
            etag=_clean_etag(response.get("ETag")),
            metadata={
                str(name): str(value)
                for name, value in response.get("Metadata", {}).items()
            },
        )

    async def signed_download_url(
        self,
        key: str,
        *,
        expires_in: int = 300,
        download_filename: str | None = None,
    ) -> str:
        key = validate_storage_key(key)
        _validate_expiry(expires_in)
        filename = safe_download_filename(download_filename)
        disposition = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
        async with self._client_factory() as client:
            return await client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentDisposition": disposition,
                },
                ExpiresIn=expires_in,
            )

    async def signed_upload_url(
        self,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        expires_in: int = 900,
    ) -> PresignedUpload:
        key = validate_storage_key(key)
        _validate_expiry(expires_in)
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive.")
        async with self._client_factory() as client:
            url = await client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ContentType": content_type,
                },
                ExpiresIn=expires_in,
            )
        return PresignedUpload(
            url=url,
            method="PUT",
            key=key,
            max_bytes=max_bytes,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
            headers={"Content-Type": content_type},
        )


def _clean_etag(value: object) -> str:
    return str(value or "").strip('"')


def _validate_expiry(expires_in: int) -> None:
    if not 1 <= expires_in <= _MAX_PRESIGN_SECONDS:
        raise ValueError("expires_in must be between 1 second and 7 days.")
