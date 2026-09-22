from __future__ import annotations

import httpx
from fastapi import FastAPI

from app.api.middleware.csrf import CSRFMiddleware


async def test_csrf_cookie_uses_shared_parent_domain() -> None:
    app = FastAPI()
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=["https://secondtrip.example.com"],
        csrf_cookie_name="st_csrf",
        cookie_domain=".secondtrip.example.com",
        cookie_secure=True,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://api.secondtrip.example.com",
    ) as client:
        response = await client.get("/health")

    cookie = response.headers["set-cookie"]
    assert "Domain=.secondtrip.example.com" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie


async def test_csrf_cookie_remains_host_only_without_a_configured_domain() -> None:
    app = FastAPI()
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=["http://localhost:3000"],
        csrf_cookie_name="st_csrf",
        cookie_domain=None,
        cookie_secure=False,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://localhost:8000",
    ) as client:
        response = await client.get("/health")

    assert "Domain=" not in response.headers["set-cookie"]
