"""Console email provider — local development. Prints the rendered email
(including the verification/reset link) to stdout instead of sending it,
so a developer never needs a real mail provider or API key to exercise
these flows locally. See docs/architecture/17-configuration.md §5.
"""

from __future__ import annotations

import structlog

from app.providers.email.base import EmailResult

log = structlog.get_logger(__name__)


class ConsoleEmailProvider:
    async def send(
        self,
        *,
        to: str,
        template_key: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailResult:
        # `to` and body content are never logged elsewhere in this app —
        # this provider is the one deliberate, local-only exception, and
        # only because there is no other way to see the link without a
        # real mail provider configured.
        print(f"\n----- console email: {template_key} -----")
        print(f"To: {to}")
        print(f"Subject: {subject}")
        print(text_body)
        print("-----------------------------------------\n")
        log.info("email.sent", provider="console", template_key=template_key)
        return EmailResult(status="sent", provider="console")
