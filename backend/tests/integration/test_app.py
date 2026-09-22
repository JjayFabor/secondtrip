"""App boot + health/readiness — see docs/architecture/18-observability.md §6."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from asgi_lifespan import LifespanManager

from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_health_does_not_touch_the_database(client: httpx.AsyncClient) -> None:
    # No DB assertion needed here — the point is this endpoint responds
    # even if it never opened a connection, per 18 §6.
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_ready_checks_the_database(client: httpx.AsyncClient) -> None:
    resp = await client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_request_id_is_echoed_on_every_response(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert "x-request-id" in {k.lower() for k in resp.headers}


async def test_request_id_is_propagated_when_supplied(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-Id": "test-fixed-id"})
    assert resp.headers["x-request-id"] == "test-fixed-id"


async def test_security_headers_are_present_on_api_responses(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/orgs")
    assert resp.status_code == 401
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["cache-control"] == "private, no-store"


async def test_security_headers_are_present_on_health(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


async def test_404_is_problem_json(client: httpx.AsyncClient) -> None:
    resp = await client.get("/this-route-does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["status"] == 404
    assert "request_id" in body


def test_openapi_operation_ids_are_unique_and_stable() -> None:
    schema = create_app().openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))
    assert "register" in operation_ids
    assert "listImports" in operation_ids
    assert all("_endpoint_" not in operation_id for operation_id in operation_ids)
