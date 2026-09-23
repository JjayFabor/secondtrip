"""Provider-neutral contact delivery."""

from __future__ import annotations

from app.modules.contact.schemas import ContactRequest
from app.providers.email.base import EmailProvider


async def deliver_contact_message(
    provider: EmailProvider,
    *,
    recipient: str | None,
    message: ContactRequest,
) -> bool:
    """Return whether the provider accepted a real message.

    A filled honeypot is intentionally indistinguishable from a successful
    submission and never reaches the provider.
    """
    if message.website:
        return True
    if not recipient:
        return False

    company = message.company or "Not provided"
    result = await provider.send(
        to=recipient,
        template_key="public_contact",
        subject=f"SecondTrip contact: {message.subject}",
        text_body=(
            "A message was submitted through the SecondTrip contact form.\n\n"
            f"Name: {message.name}\n"
            f"Email: {message.email}\n"
            f"Company: {company}\n"
            f"Subject: {message.subject}\n\n"
            f"Message:\n{message.message}\n"
        ),
    )
    return result.status == "sent"
