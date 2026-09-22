"""Email provider boundary; domain services never see a vendor SDK type."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmailResult:
    status: str  # "sent" | "failed"
    provider: str
    error: str | None = None


class EmailProvider(Protocol):
    async def send(
        self,
        *,
        to: str,
        template_key: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> EmailResult: ...
