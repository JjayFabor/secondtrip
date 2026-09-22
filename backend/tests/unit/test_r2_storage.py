from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from botocore.exceptions import ClientError

from app.composition import build_storage_provider
from app.core.settings import Settings
from app.providers.storage.r2 import R2StorageProvider


class FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0
        self.closed = False

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str, dict[str, str], str]] = {}
        self.presigns: list[tuple[str, dict[str, object], int]] = []
        self.last_body: FakeBody | None = None

    async def put_object(self, **kwargs: object) -> dict[str, Any]:
        key = str(kwargs["Key"])
        body = cast(bytes, kwargs["Body"])
        content_type = str(kwargs["ContentType"])
        metadata = dict(cast(dict[str, str], kwargs["Metadata"]))
        etag = f'etag-{len(body)}'
        self.objects[key] = (body, content_type, metadata, etag)
        return {"ETag": f'"{etag}"'}

    async def upload_fileobj(
        self,
        fileobj: Any,
        bucket: str,
        key: str,
        ExtraArgs: dict[str, object],
    ) -> None:
        del bucket
        body = fileobj.read()
        content_type = str(ExtraArgs["ContentType"])
        metadata = dict(cast(dict[str, str], ExtraArgs["Metadata"]))
        self.objects[key] = (body, content_type, metadata, f"etag-{len(body)}")

    async def get_object(self, **kwargs: object) -> dict[str, Any]:
        body, _content_type, _metadata, _etag = self.objects[str(kwargs["Key"])]
        self.last_body = FakeBody(body)
        return {"Body": self.last_body}

    async def delete_object(self, **kwargs: object) -> dict[str, Any]:
        self.objects.pop(str(kwargs["Key"]), None)
        return {}

    async def delete_objects(self, **kwargs: object) -> dict[str, Any]:
        request = kwargs["Delete"]
        assert isinstance(request, dict)
        objects = request["Objects"]
        assert isinstance(objects, list)
        for item in objects:
            assert isinstance(item, dict)
            self.objects.pop(str(item["Key"]), None)
        return {}

    async def list_objects_v2(self, **kwargs: object) -> dict[str, Any]:
        prefix = str(kwargs["Prefix"])
        matches = sorted(key for key in self.objects if key.startswith(prefix))
        start_after = str(kwargs.get("StartAfter", ""))
        remaining = [key for key in matches if key > start_after]
        page = remaining[:1]
        truncated = len(remaining) > len(page)
        response: dict[str, Any] = {
            "Contents": [{"Key": key} for key in page],
            "IsTruncated": truncated,
        }
        return response

    async def head_object(self, **kwargs: object) -> dict[str, Any]:
        key = str(kwargs["Key"])
        if key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not found"}},
                "HeadObject",
            )
        body, content_type, metadata, etag = self.objects[key]
        return {
            "ContentLength": len(body),
            "ContentType": content_type,
            "Metadata": metadata,
            "ETag": f'"{etag}"',
        }

    async def generate_presigned_url(
        self,
        client_method: str,
        *,
        Params: dict[str, object],
        ExpiresIn: int,
    ) -> str:
        self.presigns.append((client_method, Params, ExpiresIn))
        return f"https://r2.example.test/{client_method}/{Params['Key']}?signature=test"


class FakeClientContext(AbstractAsyncContextManager[FakeS3Client]):
    def __init__(self, client: FakeS3Client) -> None:
        self._client = client

    async def __aenter__(self) -> FakeS3Client:
        return self._client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback


def make_provider(client: FakeS3Client) -> R2StorageProvider:
    return R2StorageProvider(
        bucket="secondtrip-test",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="access",
        secret_access_key="secret",
        client_factory=lambda: FakeClientContext(client),
    )


async def test_r2_round_trip_streaming_and_missing_head() -> None:
    client = FakeS3Client()
    storage = make_provider(client)
    key = "orgs/one/imports/a/source.csv"

    stored = await storage.upload(
        key,
        b"job_id\n1\n",
        content_type="text/csv",
        metadata={"source": "test"},
    )
    assert stored.etag == "etag-9"
    metadata = await storage.head(key)
    assert metadata is not None
    assert metadata.key == stored.key
    assert metadata.size_bytes == stored.size_bytes
    assert metadata.content_type == stored.content_type
    assert metadata.etag == stored.etag
    assert metadata.metadata == stored.metadata
    assert b"".join([chunk async for chunk in storage.download(key)]) == b"job_id\n1\n"
    assert client.last_body is not None and client.last_body.closed

    await storage.delete(key)
    assert await storage.head(key) is None


async def test_r2_uploads_async_iterators_without_buffering_in_memory() -> None:
    client = FakeS3Client()
    storage = make_provider(client)

    async def chunks() -> AsyncIterator[bytes]:
        yield b"first,"
        yield b"second"

    stored = await storage.upload(
        "orgs/one/exports/a/report.csv",
        chunks(),
        content_type="text/csv",
    )
    assert stored.size_bytes == 12
    assert client.objects[stored.key][0] == b"first,second"


async def test_r2_delete_prefix_is_paginated_and_boundary_safe() -> None:
    client = FakeS3Client()
    storage = make_provider(client)
    for key in (
        "orgs/one/imports/a/source.csv",
        "orgs/one/imports/b/source.csv",
        "orgs/one/imports-other/keep.csv",
    ):
        await storage.upload(key, b"x", content_type="text/csv")

    assert await storage.delete_prefix("orgs/one/imports/") == 2
    assert sorted(client.objects) == ["orgs/one/imports-other/keep.csv"]


async def test_r2_presigned_urls_pin_operation_content_type_and_download_name() -> None:
    client = FakeS3Client()
    storage = make_provider(client)
    key = "orgs/one/imports/a/source.csv"

    upload = await storage.signed_upload_url(
        key,
        content_type="text/csv",
        max_bytes=1024,
        expires_in=900,
    )
    download = await storage.signed_download_url(
        key,
        download_filename="../../jobs report.csv",
        expires_in=300,
    )

    assert upload.method == "PUT"
    assert upload.max_bytes == 1024
    assert upload.headers == {"Content-Type": "text/csv"}
    assert download.startswith("https://r2.example.test/get_object/")
    assert client.presigns[0] == (
        "put_object",
        {"Bucket": "secondtrip-test", "Key": key, "ContentType": "text/csv"},
        900,
    )
    assert client.presigns[1][0] == "get_object"
    assert client.presigns[1][1]["ResponseContentDisposition"] == (
        "attachment; filename*=UTF-8''_.._jobs%20report.csv"
    )


def test_composition_builds_r2_from_validated_settings(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "storage_provider": "r2",
            "storage_bucket": "secondtrip-test",
            "storage_endpoint_url": "https://account.r2.cloudflarestorage.com",
            "storage_access_key_id": "access",
            "storage_secret_access_key": "secret",
        }
    )
    assert isinstance(build_storage_provider(configured), R2StorageProvider)


async def test_real_r2_sdk_generates_sigv4_urls_without_network_access() -> None:
    storage = R2StorageProvider(
        bucket="secondtrip-test",
        endpoint_url="https://account.r2.cloudflarestorage.com",
        access_key_id="access",
        secret_access_key="secret",
    )
    key = "orgs/one/imports/a/source.csv"

    upload = await storage.signed_upload_url(
        key,
        content_type="text/csv",
        max_bytes=1024,
    )
    download = await storage.signed_download_url(key, download_filename="jobs.csv")

    upload_query = parse_qs(urlsplit(upload.url).query)
    download_query = parse_qs(urlsplit(download).query)
    assert upload_query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert upload_query["X-Amz-SignedHeaders"] == ["content-type;host"]
    assert download_query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
