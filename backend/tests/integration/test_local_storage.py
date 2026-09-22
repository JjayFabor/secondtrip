from __future__ import annotations

from uuid import uuid4

import httpx
from asgi_lifespan import LifespanManager

from app.composition import AppState
from app.main import create_app
from app.providers.storage.local import LocalStorageProvider


async def test_signed_local_upload_and_download_need_no_session_or_csrf() -> None:
    app = create_app()
    async with LifespanManager(app):
        state: AppState = app.state.app_state
        assert isinstance(state.storage_provider, LocalStorageProvider)
        key = f"orgs/{uuid4()}/imports/{uuid4()}/source.csv"
        upload = await state.storage_provider.signed_upload_url(
            key,
            content_type="text/csv",
            max_bytes=1024,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.put(
                upload.url,
                content=b"job_id\n1\n",
                headers={"Content-Type": "text/csv"},
            )
            assert response.status_code == 204

            download_url = await state.storage_provider.signed_download_url(
                key,
                download_filename="jobs.csv",
            )
            response = await client.get(download_url)
            assert response.status_code == 200
            assert response.content == b"job_id\n1\n"
            assert response.headers["content-disposition"] == (
                "attachment; filename*=UTF-8''jobs.csv"
            )
        await state.storage_provider.delete(key)


async def test_signed_local_upload_enforces_size_before_writing() -> None:
    app = create_app()
    async with LifespanManager(app):
        state: AppState = app.state.app_state
        assert isinstance(state.storage_provider, LocalStorageProvider)
        key = f"orgs/{uuid4()}/imports/{uuid4()}/source.csv"
        upload = await state.storage_provider.signed_upload_url(
            key,
            content_type="text/csv",
            max_bytes=3,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport) as client:
            response = await client.put(
                upload.url,
                content=b"four",
                headers={"Content-Type": "text/csv"},
            )
        assert response.status_code == 413
        assert await state.storage_provider.head(key) is None
