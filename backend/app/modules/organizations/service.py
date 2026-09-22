"""Organizations service. See docs/architecture/02-multi-tenancy.md §3
and 03-authentication.md §4 (invitations).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.permissions import OrganizationRole
from app.core.security import hash_token, new_bearer_token
from app.core.settings import Settings
from app.modules.detection.reviews import ensure_review_taxonomy
from app.modules.detection.service import ensure_default_rule_set
from app.modules.organizations.errors import InvitationEmailMismatchError, LastOwnerError
from app.modules.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)
from app.modules.organizations.repository import OrganizationsRepository

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9-]+")
_SLUG_RESERVED = frozenset({"app", "api", "www", "admin", "auth", "login", "register", "settings"})


async def get_organization_timezone(session: AsyncSession, organization_id: UUID) -> str:
    """Public read boundary for workers that need organization-local date semantics."""
    organization = await OrganizationsRepository(session).get_organization(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found.")
    return organization.timezone


@dataclass(frozen=True, slots=True)
class OrganizationImportSettings:
    timezone: str
    currency_code: str


async def get_organization_import_settings(
    session: AsyncSession, organization_id: UUID
) -> OrganizationImportSettings:
    """Public organization boundary for import normalization and money defaults."""
    organization = await OrganizationsRepository(session).get_organization(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found.")
    return OrganizationImportSettings(organization.timezone, organization.currency_code)


async def _generate_unique_slug(repo: OrganizationsRepository, name: str) -> str:
    base = _SLUG_INVALID_CHARS.sub("-", name.strip().lower().replace(" ", "-")).strip("-") or "org"
    if base in _SLUG_RESERVED:
        base = f"{base}-org"
    candidate = base
    suffix = 1
    while await repo.get_organization_by_slug(candidate) is not None:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


async def create_organization(
    session: AsyncSession,
    repo: OrganizationsRepository,
    settings: Settings,
    *,
    name: str,
    owner_user_id: UUID,
) -> Organization:
    slug = await _generate_unique_slug(repo, name)
    org = await repo.create_organization(name=name, slug=slug, created_by_user_id=owner_user_id)
    # The route begins with a user-scoped transaction because there is no org
    # context yet. Set the new org before the first tenant-owned insert so
    # RLS's WITH CHECK policy can authorize the owner membership.
    await repo.set_organization_context(org.id)
    await repo.create_membership(
        organization_id=org.id,
        user_id=owner_user_id,
        role=OrganizationRole.OWNER.value,
        invited_by_user_id=None,
    )
    await ensure_default_rule_set(
        session,
        settings,
        organization_id=org.id,
        created_by_user_id=owner_user_id,
    )
    await ensure_review_taxonomy(session, organization_id=org.id)
    return org


async def invite_member(
    org_repo: OrganizationsRepository,
    settings: Settings,
    *,
    organization_id: UUID,
    organization_name: str,
    inviter_user_id: UUID,
    email: str,
    role: OrganizationRole,
) -> tuple[OrganizationInvitation, InvitationDelivery]:
    if role is OrganizationRole.OWNER:
        raise ConflictError("Invite as admin and transfer ownership afterward, if needed.")

    existing = await org_repo.get_pending_invitation(organization_id, email)
    if existing is not None:
        existing.revoked_at = datetime.now(UTC)

    now = datetime.now(UTC)
    raw_token = new_bearer_token()
    invitation = await org_repo.create_invitation(
        organization_id=organization_id,
        email=email,
        role=role.value,
        token_hash=hash_token(raw_token),
        invited_by_user_id=inviter_user_id,
        expires_at=now + timedelta(days=settings.invitation_ttl_days),
    )
    accept_url = f"{settings.frontend_url}/accept-invite?token={raw_token}"
    return invitation, InvitationDelivery(
        to=email,
        template_key="organization_invitation",
        subject=f"You've been invited to join {organization_name} on SecondTrip",
        text_body=(
            f"You've been invited to join {organization_name} on SecondTrip as {role.value}.\n\n"
            f"Accept the invitation:\n\n{accept_url}\n\n"
            f"This link expires in {settings.invitation_ttl_days} days."
        ),
    )


@dataclass(frozen=True, slots=True)
class InvitationDelivery:
    to: str
    template_key: str
    subject: str
    text_body: str


async def resend_invitation(
    settings: Settings,
    *,
    invitation: OrganizationInvitation,
) -> InvitationDelivery:
    now = datetime.now(UTC)
    raw_token = new_bearer_token()
    invitation.token_hash = hash_token(raw_token)
    invitation.expires_at = now + timedelta(days=settings.invitation_ttl_days)
    invitation.revoked_at = None
    invitation.accepted_at = None
    invitation.accepted_by_user_id = None
    accept_url = f"{settings.frontend_url}/accept-invite?token={raw_token}"
    return InvitationDelivery(
        to=invitation.email,
        template_key="organization_invitation",
        subject="Your SecondTrip invitation was resent",
        text_body=(
            "Your invitation to join SecondTrip is still waiting.\n\n"
            f"Accept the invitation:\n\n{accept_url}\n\n"
            f"This link expires in {settings.invitation_ttl_days} days."
        ),
    )


async def resolve_invitation_by_token(
    org_repo: OrganizationsRepository, *, raw_token: str
) -> OrganizationInvitation:
    """Called within a token_lookup_session — see db/session.py."""
    invitation = await org_repo.get_invitation_by_token(hash_token(raw_token))
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or invitation.expires_at < now
    ):
        raise NotFoundError("This invitation is invalid or has expired.")
    return invitation


async def accept_invitation(
    org_repo: OrganizationsRepository,
    *,
    invitation: OrganizationInvitation,
    accepting_user_id: UUID,
    accepting_user_email: str,
) -> OrganizationMembership:
    """Called within a tenant_session scoped to invitation.organization_id
    — see api routers. The email-binding check (03 §4) happens here, not
    only at token-resolution time, so a token can't be resolved once and
    replayed against a different account."""
    if accepting_user_email.lower() != invitation.email.lower():
        raise InvitationEmailMismatchError("This invitation was sent to a different email address.")

    existing = await org_repo.get_active_membership(invitation.organization_id, accepting_user_id)
    if existing is not None:
        invitation.accepted_at = datetime.now(UTC)
        invitation.accepted_by_user_id = accepting_user_id
        return existing

    membership = await org_repo.create_membership(
        organization_id=invitation.organization_id,
        user_id=accepting_user_id,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
    )
    invitation.accepted_at = datetime.now(UTC)
    invitation.accepted_by_user_id = accepting_user_id
    return membership


async def revoke_invitation(
    org_repo: OrganizationsRepository, *, invitation: OrganizationInvitation
) -> None:
    invitation.revoked_at = datetime.now(UTC)


async def change_member_role(
    org_repo: OrganizationsRepository,
    *,
    organization_id: UUID,
    target_membership: OrganizationMembership,
    new_role: OrganizationRole,
    acting_role: OrganizationRole,
) -> None:
    demoting_the_owner = (
        target_membership.role == OrganizationRole.OWNER.value
        and new_role is not OrganizationRole.OWNER
    )
    if demoting_the_owner and await org_repo.count_active_owners(organization_id) <= 1:
        raise LastOwnerError(
            "This is the only owner. Transfer ownership before changing this role."
        )
    if new_role is OrganizationRole.OWNER and acting_role is not OrganizationRole.OWNER:
        raise ForbiddenError("Only an owner can grant ownership.")
    target_membership.role = new_role.value


async def remove_member(
    org_repo: OrganizationsRepository,
    *,
    organization_id: UUID,
    target_membership: OrganizationMembership,
) -> None:
    is_owner = target_membership.role == OrganizationRole.OWNER.value
    if is_owner and await org_repo.count_active_owners(organization_id) <= 1:
        raise LastOwnerError("This is the only owner. Transfer ownership before removing them.")
    target_membership.revoked_at = datetime.now(UTC)


async def transfer_ownership(
    org_repo: OrganizationsRepository,
    *,
    organization_id: UUID,
    from_membership: OrganizationMembership,
    to_membership: OrganizationMembership,
) -> None:
    from_membership.role = OrganizationRole.ADMIN.value
    to_membership.role = OrganizationRole.OWNER.value


async def get_organizations_by_ids(
    organizations_repo: OrganizationsRepository, ids: list[UUID]
) -> dict[UUID, Organization]:
    """Small helper for 'list my orgs': batch-fetch org rows for a set of
    membership rows. Runs in the SAME user_session as the membership
    query — organizations has no RLS, so this needs no special
    context, but reusing the open session avoids opening a second one."""
    result: dict[UUID, Organization] = {}
    for org_id in ids:
        org = await organizations_repo.get_organization(org_id)
        if org is not None:
            result[org_id] = org
    return result
