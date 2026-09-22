"""Resend email provider. See docs/architecture/17-configuration.md §5.

Written to Resend's documented REST API; not exercised against a live
account in this environment (no API key configured here) — same caveat
as the GitHub Actions workflows in docs/architecture/16 §5: correct by
inspection and by matching the documented API shape, not yet verified
live. Confirm against a real Resend account before relying on it.
Vendor confinement applies here — `httpx` calling
Resend's API is the only thing in this file that talks to the vendor;
callers only ever see `EmailResult`.
"""

from __future__ import annotations

import httpx
import structlog

from app.providers.email.base import EmailResult

log = structlog.get_logger(__name__)

_RESEND_API_URL = "https://api.resend.com/emails"


class ResendEmailProvider:
    def __init__(self, *, api_key: str, from_address: str, from_name: str = "SecondTrip") -> None:
        self._api_key = api_key
        self._from = f"{from_name} <{from_address}>"

    async def send(
        self,
        *,
        to: str,
        template_key: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailResult:
        payload: dict[str, object] = {
            "from": self._from,
            "to": [to],
            "subject": subject,
            "text": text_body,
        }
        if html_body:
            payload["html"] = html_body

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _RESEND_API_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            if response.status_code >= 400:
                log.warning(
                    "email.send_failed",
                    provider="resend",
                    template_key=template_key,
                    status=response.status_code,
                )
                return EmailResult(
                    status="failed", provider="resend", error=f"HTTP {response.status_code}"
                )
        except httpx.HTTPError as exc:
            log.warning("email.send_failed", provider="resend", template_key=template_key)
            return EmailResult(status="failed", provider="resend", error=str(exc))

        log.info("email.sent", provider="resend", template_key=template_key)
        return EmailResult(status="sent", provider="resend")
