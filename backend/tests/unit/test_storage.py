from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import EntitlementExceededError
from app.modules.imports.service import verify_uploaded_object
from app.providers.storage.keys import (
    safe_download_filename,
    validate_storage_key,
    validate_storage_prefix,
)
from app.providers.storage.local import InvalidStorageToken, LocalStorageProvider
from app.providers.storage.memory import InMemoryStorageProvider


@pytest.mark.parametrize(
    "key",
    ["", "/absolute.csv", "../escape.csv", "orgs/../escape.csv", "orgs/./file.csv"],
)
def test_storage_keys_reject_path_traversal(key: str) -> None:
    with pytest.raises(ValueError):
        validate_storage_key(key)


def test_download_filename_is_display_only_and_sanitized() -> None:
    assert safe_download_filename("../../secret\n.csv") == "_.._secret.csv"
    assert safe_download_filename("...") == "download.csv"


def test_storage_prefix_accepts_one_optional_trailing_slash() -> None:
    assert validate_storage_prefix("orgs/one/imports") == "orgs/one/imports/"
    assert validate_storage_prefix("orgs/one/imports/") == "orgs/one/imports/"


async def test_memory_storage_round_trip_and_prefix_delete() -> None:
    storage = InMemoryStorageProvider()
    first = await storage.upload(
        "orgs/one/imports/a/source.csv",
        b"job_id\n1\n",
        content_type="text/csv",
    )
    await storage.upload(
        "orgs/one/imports/b/source.csv",
        b"job_id\n2\n",
        content_type="text/csv",
    )
    assert first.size_bytes == 9
    assert b"".join([chunk async for chunk in storage.download(first.key)]) == b"job_id\n1\n"
    assert await storage.delete_prefix("orgs/one/imports") == 2
    assert await storage.head(first.key) is None


async def test_oversized_upload_is_deleted_after_verification() -> None:
    storage = InMemoryStorageProvider()
    key = "orgs/one/imports/a/source.csv"
    await storage.upload(key, b"four", content_type="text/csv")

    with pytest.raises(EntitlementExceededError):
        await verify_uploaded_object(storage, key, max_bytes=3)

    assert await storage.head(key) is None


async def test_local_storage_tokens_are_operation_bound_and_tamper_evident(
    tmp_path: Path,
) -> None:
    storage = LocalStorageProvider(
        root=tmp_path,
        app_secret="a" * 32,
        base_url="http://localhost:8000",
    )
    upload = await storage.signed_upload_url(
        "orgs/one/imports/a/source.csv",
        content_type="text/csv",
        max_bytes=1024,
    )
    token = upload.url.rsplit("/", maxsplit=1)[-1]
    assert storage.verify_token(token, operation="upload")["max_bytes"] == 1024
    with pytest.raises(InvalidStorageToken):
        storage.verify_token(token, operation="download")
    with pytest.raises(InvalidStorageToken):
        storage.verify_token(token + "x", operation="upload")
