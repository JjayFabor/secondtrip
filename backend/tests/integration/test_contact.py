"""Public contact form validation, abuse controls, and provider behavior."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import uuid4

import httpx
from asgi_lifespan import LifespanManager

from app.core.settings import Settings
from app.main import create_app
from app.providers.email.base import EmailResult


@dataclass(slots=True)
class RecordingEmailProvider:
    status: str = "sent"
    calls: list[dict[str, str]] = field(default_factory=list)

    async def send(
        self,
        *,
        to: str,
        template_key: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailResult:
        self.calls.append(
            {
                "to": to,
                "template_key": template_key,
                "subject": subject,
                "text_body": text_body,
            }
        )
        return EmailResult(
            status=self.status,
            provider="test",
            error="provider-private-detail" if self.status == "failed" else None,
        )


@asynccontextmanager
async def contact_client(
    settings: Settings,
    provider: RecordingEmailProvider,
    *,
    recipient: str | None = "support@example.test",
    limit: int = 5,
) -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    app = create_app()
    async with LifespanManager(app):
        app.state.app_state.settings = settings.model_copy(
            update={
                "contact_recipient_address": recipient,
                "contact_ip_limit": limit,
            }
        )
        app.state.app_state.email_provider = provider
        unique_client_ip = f"contact-test-{uuid4()}.invalid"
        transport = httpx.ASGITransport(
            app=app,
            client=(unique_client_ip, 43210),
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            bootstrap = await client.get("/health")
            assert bootstrap.status_code == 200
            csrf = client.cookies.get(settings.csrf_cookie_name)
            assert csrf is not None
            yield client, {
                "Origin": settings.frontend_url,
                "X-CSRF-Token": csrf,
            }


def valid_message() -> dict[str, str]:
    return {
        "name": "Avery Manager",
        "email": "avery@example.com",
        "company": "Clear Day Service",
        "subject": "Private beta question",
        "message": "Could we discuss whether our service history is a good fit?",
        "website": "",
    }


async def test_contact_rejects_invalid_and_extra_fields(settings: Settings) -> None:
    provider = RecordingEmailProvider()
    async with contact_client(settings, provider) as (client, headers):
        body = valid_message()
        body["email"] = "not-an-email"
        body["unexpected"] = "rejected"
        response = await client.post("/api/v1/contact", headers=headers, json=body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert provider.calls == []


async def test_contact_honeypot_returns_generic_success_without_sending(
    settings: Settings,
) -> None:
    provider = RecordingEmailProvider()
    async with contact_client(settings, provider) as (client, headers):
        body = valid_message()
        body["website"] = "https://spam.example"
        response = await client.post("/api/v1/contact", headers=headers, json=body)

    assert response.status_code == 202
    assert response.json() == {"detail": "Thanks. Your message has been received."}
    assert provider.calls == []


async def test_contact_sends_through_email_provider(settings: Settings) -> None:
    provider = RecordingEmailProvider()
    async with contact_client(settings, provider) as (client, headers):
        response = await client.post(
            "/api/v1/contact",
            headers=headers,
            json=valid_message(),
        )

    assert response.status_code == 202
    assert len(provider.calls) == 1
    assert provider.calls[0]["to"] == "support@example.test"
    assert provider.calls[0]["template_key"] == "public_contact"


async def test_contact_is_rate_limited_per_hashed_client_address(
    settings: Settings,
) -> None:
    provider = RecordingEmailProvider()
    async with contact_client(settings, provider, limit=1) as (client, headers):
        first = await client.post("/api/v1/contact", headers=headers, json=valid_message())
        second = await client.post("/api/v1/contact", headers=headers, json=valid_message())

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json()["code"] == "RATE_LIMITED"
    assert len(provider.calls) == 1


async def test_contact_provider_failure_is_generic(settings: Settings) -> None:
    provider = RecordingEmailProvider(status="failed")
    async with contact_client(settings, provider) as (client, headers):
        response = await client.post(
            "/api/v1/contact",
            headers=headers,
            json=valid_message(),
        )

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "provider-private-detail" not in response.text


async def test_contact_is_clear_when_recipient_is_not_configured(settings: Settings) -> None:
    provider = RecordingEmailProvider()
    async with contact_client(settings, provider, recipient=None) as (client, headers):
        response = await client.post(
            "/api/v1/contact",
            headers=headers,
            json=valid_message(),
        )

    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert provider.calls == []
