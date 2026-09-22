"""Capability-URL endpoint used only by the local storage adapter."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse

from app.composition import AppState, get_app_state
from app.providers.storage.local import InvalidStorageToken, LocalStorageProvider

router = APIRouter(prefix="/storage/local", tags=["local-storage"])


def _local_provider(app_state: AppState) -> LocalStorageProvider:
    provider = app_state.storage_provider
    if not isinstance(provider, LocalStorageProvider):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")
    return provider


@router.put("/{token}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def upload_local_object(
    token: str,
    request: Request,
    app_state: AppState = Depends(get_app_state),
) -> Response:
    provider = _local_provider(app_state)
    try:
        payload = provider.verify_token(token, operation="upload")
    except InvalidStorageToken as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    expected_type = str(payload["content_type"])
    if request.headers.get("content-type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content-Type must be {expected_type}.",
        )
    max_bytes = int(payload["max_bytes"])
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_bytes = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content-Length must be an integer.",
            ) from exc
        if declared_bytes > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Upload exceeds the signed size limit.",
            )

    async def limited_body() -> AsyncIterator[bytes]:
        received = 0
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Upload exceeds the signed size limit.",
                )
            yield chunk

    await provider.upload(
        str(payload["key"]),
        limited_body(),
        content_type=expected_type,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{token}", include_in_schema=False)
async def download_local_object(
    token: str,
    app_state: AppState = Depends(get_app_state),
) -> StreamingResponse:
    provider = _local_provider(app_state)
    try:
        payload = provider.verify_token(token, operation="download")
    except InvalidStorageToken as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    key = str(payload["key"])
    metadata = await provider.head(key)
    if metadata is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object not found.")
    filename = quote(str(payload["filename"]), safe="")
    return StreamingResponse(
        provider.download(key),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
            "Content-Length": str(metadata.size_bytes),
        },
    )
