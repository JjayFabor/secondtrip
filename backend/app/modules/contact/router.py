"""Public contact endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.composition import AppState, get_app_state
from app.core.errors import ServiceUnavailableError
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_ip
from app.modules.contact.schemas import ContactRequest, ContactResponse
from app.modules.contact.service import deliver_contact_message

router = APIRouter(tags=["contact"])

_SUCCESS = "Thanks. Your message has been received."


def get_contact_ip_hash(
    request: Request,
    app_state: AppState = Depends(get_app_state),
) -> str | None:
    if request.client is None:
        return None
    return hash_ip(request.client.host, app_secret=app_state.settings.app_secret)


@router.post(
    "/contact",
    response_model=ContactResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_contact_endpoint(
    body: ContactRequest,
    app_state: AppState = Depends(get_app_state),
    ip_hash: str | None = Depends(get_contact_ip_hash),
) -> ContactResponse:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"contact:ip:{ip_hash or 'unknown'}",
        limit=app_state.settings.contact_ip_limit,
        window_seconds=app_state.settings.contact_ip_window_seconds,
    )
    delivered = await deliver_contact_message(
        app_state.email_provider,
        recipient=app_state.settings.contact_recipient_address,
        message=body,
    )
    if not delivered:
        raise ServiceUnavailableError(
            "The contact form is not available right now. Please try again later."
        )
    return ContactResponse(detail=_SUCCESS)
