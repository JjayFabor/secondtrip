"""Organizations, members, and invitations routes.
See docs/architecture/15-api-design.md §2.
"""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.errors import InvalidCursorRequestError, NotFoundError
from app.core.pagination import InvalidCursorError, clamp_limit
from app.core.permissions import OrganizationRole, Permission
from app.core.rate_limit import enforce_rate_limit
from app.core.security import hash_token
from app.core.tenancy import TenantContext
from app.db.session import tenant_session, token_lookup_session
from app.modules.audit.schemas import ActorType, AuditEventOut, AuditListOut, AuditPageOut
from app.modules.audit.service import list_events
from app.modules.audit.service import record as record_audit
from app.modules.identity.deps import AuthenticatedUser, get_user_scoped_session, require_session
from app.modules.organizations.deps import (
    get_tenant_session,
    require_org_context,
    require_permission,
)
from app.modules.organizations.repository import OrganizationsRepository
from app.modules.organizations.schemas import (
    AcceptInvitationRequest,
    ChangeRoleRequest,
    CreateOrganizationRequest,
    InvitationOut,
    InvitationPreviewOut,
    InviteMemberRequest,
    MembershipOut,
    MyInvitationOut,
    MyOrganizationOut,
    OrganizationOut,
    TransferOwnershipRequest,
)
from app.modules.organizations.service import (
    accept_invitation,
    change_member_role,
    create_organization,
    get_organizations_by_ids,
    invite_member,
    remove_member,
    resend_invitation,
    resolve_invitation_by_token,
    revoke_invitation,
    transfer_ownership,
)
from app.shared.csv_safety import csv_safe

orgs_router = APIRouter(prefix="/orgs", tags=["organizations"])
invitations_router = APIRouter(prefix="/auth/invitations", tags=["invitations"])
me_org_router = APIRouter(prefix="/me", tags=["me"])

# Named once at module scope rather than called inline in each endpoint's
# defaults: `require_permission(...)` returns a stateless closure (it
# only closes over an immutable Permission value), so reusing one
# instance across every request for a given permission is exactly right
# — and it reads better than a lambda-shaped inline call in a signature.
require_members_read = require_permission(Permission.MEMBERS_READ)
require_members_manage = require_permission(Permission.MEMBERS_MANAGE)
require_ownership_transfer = require_permission(Permission.OWNERSHIP_TRANSFER)
require_invitations_manage = require_permission(Permission.INVITATIONS_MANAGE)
require_audit_read = require_permission(Permission.AUDIT_READ)


@me_org_router.get("/invitations")
async def list_my_invitations_endpoint(
    session: AsyncSession = Depends(get_user_scoped_session),
    user: AuthenticatedUser = Depends(require_session),
) -> list[MyInvitationOut]:
    org_repo = OrganizationsRepository(session)
    invitations = await org_repo.list_pending_invitations_for_email(user.email)
    orgs = await get_organizations_by_ids(
        org_repo, [invitation.organization_id for invitation in invitations]
    )
    return [
        MyInvitationOut(
            id=invitation.id,
            organization_id=invitation.organization_id,
            organization_name=orgs[invitation.organization_id].name,
            email=invitation.email,
            role=OrganizationRole(invitation.role),
            expires_at=invitation.expires_at,
        )
        for invitation in invitations
        if invitation.organization_id in orgs
    ]


@orgs_router.get("")
async def list_my_organizations_endpoint(
    session: AsyncSession = Depends(get_user_scoped_session),
    user: AuthenticatedUser = Depends(require_session),
) -> list[MyOrganizationOut]:
    org_repo = OrganizationsRepository(session)
    memberships = await org_repo.list_my_memberships()
    orgs = await get_organizations_by_ids(org_repo, [m.organization_id for m in memberships])
    return [
        MyOrganizationOut(
            id=org.id,
            name=org.name,
            slug=org.slug,
            timezone=org.timezone,
            currency_code=org.currency_code,
            status=org.status,
            role=OrganizationRole(m.role),
        )
        for m in memberships
        if (org := orgs.get(m.organization_id)) is not None
    ]


@orgs_router.post("")
async def create_organization_endpoint(
    body: CreateOrganizationRequest,
    request: Request,
    state: AppState = Depends(get_app_state),
    session: AsyncSession = Depends(get_user_scoped_session),
    user: AuthenticatedUser = Depends(require_session),
) -> OrganizationOut:
    org_repo = OrganizationsRepository(session)
    org = await create_organization(
        session,
        org_repo,
        state.settings,
        name=body.name,
        owner_user_id=user.id,
    )
    await record_audit(
        session,
        organization_id=org.id,
        action="organization.created",
        summary=f"Created organization {org.name}",
        actor_type=ActorType.USER,
        actor_user_id=user.id,
        actor_label=user.full_name,
        resource_type="organization",
        resource_id=org.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return OrganizationOut.model_validate(org)


@orgs_router.get("/{org_id}")
async def get_organization_endpoint(
    org_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_org_context),
) -> OrganizationOut:
    org_repo = OrganizationsRepository(session)
    org = await org_repo.get_organization(org_id)
    if org is None:
        raise NotFoundError("Organization not found.")
    return OrganizationOut.model_validate(org)


@orgs_router.get("/{org_id}/members")
async def list_members_endpoint(
    org_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_members_read),
) -> list[MembershipOut]:
    org_repo = OrganizationsRepository(session)
    members = await org_repo.list_active_members(org_id)
    return [MembershipOut.model_validate(m) for m in members]


@orgs_router.patch("/{org_id}/members/{user_id}")
async def change_member_role_endpoint(
    org_id: UUID,
    user_id: UUID,
    body: ChangeRoleRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_members_manage),
) -> MembershipOut:
    org_repo = OrganizationsRepository(session)
    target = await org_repo.get_active_membership(org_id, user_id)
    if target is None:
        raise NotFoundError("Member not found.")
    assert tenant.role is not None
    await change_member_role(
        org_repo,
        organization_id=org_id,
        target_membership=target,
        new_role=body.role,
        acting_role=tenant.role,
    )
    await record_audit(
        session,
        organization_id=org_id,
        action="member.role_changed",
        summary=f"Changed a member's role to {body.role.value}",
        actor_user_id=tenant.actor_user_id,
        resource_type="organization_membership",
        resource_id=target.id,
        changes={"role": body.role.value},
        request_id=getattr(request.state, "request_id", None),
    )
    return MembershipOut.model_validate(target)


@orgs_router.delete("/{org_id}/members/{user_id}", status_code=204)
async def remove_member_endpoint(
    org_id: UUID,
    user_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_members_manage),
) -> None:
    org_repo = OrganizationsRepository(session)
    target = await org_repo.get_active_membership(org_id, user_id)
    if target is None:
        raise NotFoundError("Member not found.")
    await remove_member(org_repo, organization_id=org_id, target_membership=target)
    await record_audit(
        session,
        organization_id=org_id,
        action="member.removed",
        summary="Removed a member",
        actor_user_id=tenant.actor_user_id,
        resource_type="organization_membership",
        resource_id=target.id,
        request_id=getattr(request.state, "request_id", None),
    )


@orgs_router.post("/{org_id}/members/transfer-ownership", status_code=204)
async def transfer_ownership_endpoint(
    org_id: UUID,
    body: TransferOwnershipRequest,
    request: Request,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_ownership_transfer),
) -> None:
    org_repo = OrganizationsRepository(session)
    assert tenant.actor_user_id is not None
    from_membership = await org_repo.get_active_membership(org_id, tenant.actor_user_id)
    to_membership = await org_repo.get_active_membership(org_id, body.to_user_id)
    if from_membership is None or to_membership is None:
        raise NotFoundError("Member not found.")
    await transfer_ownership(
        org_repo,
        organization_id=org_id,
        from_membership=from_membership,
        to_membership=to_membership,
    )
    await record_audit(
        session,
        organization_id=org_id,
        action="member.ownership_transferred",
        summary="Transferred organization ownership",
        actor_user_id=tenant.actor_user_id,
        resource_type="organization_membership",
        resource_id=to_membership.id,
        changes={"from_user_id": str(tenant.actor_user_id), "to_user_id": str(body.to_user_id)},
        request_id=getattr(request.state, "request_id", None),
    )


@orgs_router.get("/{org_id}/invitations")
async def list_invitations_endpoint(
    org_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_invitations_manage),
) -> list[InvitationOut]:
    org_repo = OrganizationsRepository(session)
    invitations = await org_repo.list_pending_invitations(org_id)
    return [InvitationOut.model_validate(i) for i in invitations]


@orgs_router.get("/{org_id}/audit", response_model=AuditListOut)
async def list_audit_endpoint(
    org_id: UUID,
    action: str | None = None,
    actor_user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    cursor: str | None = None,
    limit: int | None = Query(default=None, ge=1, le=200),
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_audit_read),
) -> AuditListOut:
    page_limit = clamp_limit(limit)
    try:
        events, next_cursor = await list_events(
            session,
            organization_id=org_id,
            action=action,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
            cursor=cursor,
            limit=page_limit,
        )
    except (InvalidCursorError, ValueError) as exc:
        raise InvalidCursorRequestError("Cursor is malformed or expired.") from exc
    return AuditListOut(
        data=[AuditEventOut.model_validate(event) for event in events],
        page=AuditPageOut(
            next_cursor=next_cursor, has_more=next_cursor is not None, limit=page_limit
        ),
    )


@orgs_router.get("/{org_id}/audit/export")
async def export_audit_endpoint(
    org_id: UUID,
    action: str | None = None,
    actor_user_id: UUID | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: int = Query(default=5000, ge=1, le=10000),
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_audit_read),
) -> Response:
    events, _ = await list_events(
        session,
        organization_id=org_id,
        action=action,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=limit,
    )
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "occurred_at",
            "actor_type",
            "actor_user_id",
            "actor_label",
            "action",
            "resource_type",
            "resource_id",
            "summary",
            "changes",
            "request_id",
        ]
    )
    for event in events:
        writer.writerow(
            [
                csv_safe(event.id),
                csv_safe(event.occurred_at),
                csv_safe(event.actor_type),
                csv_safe(event.actor_user_id),
                csv_safe(event.actor_label),
                csv_safe(event.action),
                csv_safe(event.resource_type),
                csv_safe(event.resource_id),
                csv_safe(event.summary),
                csv_safe(event.changes),
                csv_safe(event.request_id),
            ]
        )
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )


@orgs_router.post("/{org_id}/invitations")
async def create_invitation_endpoint(
    org_id: UUID,
    body: InviteMemberRequest,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_invitations_manage),
) -> InvitationOut:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"org:{org_id}:invitation-send",
        limit=app_state.settings.invitation_org_limit,
        window_seconds=app_state.settings.invitation_org_window_seconds,
    )
    async with tenant_session(app_state.session_factory, tenant) as session:
        org_repo = OrganizationsRepository(session)
        org = await org_repo.get_organization(org_id)
        if org is None:
            raise NotFoundError("Organization not found.")
        assert tenant.actor_user_id is not None
        invitation, delivery = await invite_member(
            org_repo,
            app_state.settings,
            organization_id=org_id,
            organization_name=org.name,
            inviter_user_id=tenant.actor_user_id,
            email=body.email,
            role=body.role,
        )
        await record_audit(
            session,
            organization_id=org_id,
            action="member.invited",
            summary=f"Invited a new {body.role.value}",
            actor_user_id=tenant.actor_user_id,
            resource_type="organization_invitation",
            resource_id=invitation.id,
            changes={"role": body.role.value},
            request_id=getattr(request.state, "request_id", None),
        )
    await app_state.email_provider.send(
        to=delivery.to,
        template_key=delivery.template_key,
        subject=delivery.subject,
        text_body=delivery.text_body,
    )
    return InvitationOut.model_validate(invitation)


@orgs_router.post("/{org_id}/invitations/{invitation_id}/resend")
async def resend_invitation_endpoint(
    org_id: UUID,
    invitation_id: UUID,
    request: Request,
    app_state: AppState = Depends(get_app_state),
    tenant: TenantContext = Depends(require_invitations_manage),
) -> InvitationOut:
    await enforce_rate_limit(
        app_state.session_factory,
        key=f"org:{org_id}:invitation-send",
        limit=app_state.settings.invitation_org_limit,
        window_seconds=app_state.settings.invitation_org_window_seconds,
    )
    async with tenant_session(app_state.session_factory, tenant) as session:
        org_repo = OrganizationsRepository(session)
        invitation = await org_repo.get_invitation(org_id, invitation_id, for_update=True)
        if invitation is None or invitation.accepted_at is not None:
            raise NotFoundError("Invitation not found.")
        delivery = await resend_invitation(app_state.settings, invitation=invitation)
        await record_audit(
            session,
            organization_id=org_id,
            action="member.invitation_resent",
            summary="Resent an organization invitation",
            actor_user_id=tenant.actor_user_id,
            resource_type="organization_invitation",
            resource_id=invitation.id,
            request_id=getattr(request.state, "request_id", None),
        )
    await app_state.email_provider.send(
        to=delivery.to,
        template_key=delivery.template_key,
        subject=delivery.subject,
        text_body=delivery.text_body,
    )
    return InvitationOut.model_validate(invitation)


@orgs_router.delete("/{org_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation_endpoint(
    org_id: UUID,
    invitation_id: UUID,
    session: AsyncSession = Depends(get_tenant_session),
    tenant: TenantContext = Depends(require_invitations_manage),
) -> None:
    org_repo = OrganizationsRepository(session)
    invitation = await org_repo.get_invitation(org_id, invitation_id)
    if invitation is None:
        raise NotFoundError("Invitation not found.")
    await revoke_invitation(org_repo, invitation=invitation)


# --- invitation preview + accept — token-authenticated, not org-scoped ----


@invitations_router.get("/{token}")
async def preview_invitation_endpoint(
    token: str, app_state: AppState = Depends(get_app_state)
) -> InvitationPreviewOut:
    async with token_lookup_session(app_state.session_factory, hash_token(token)) as session:
        org_repo = OrganizationsRepository(session)
        invitation = await resolve_invitation_by_token(org_repo, raw_token=token)
        org = await org_repo.get_organization(invitation.organization_id)
        assert org is not None
        return InvitationPreviewOut(
            organization_name=org.name,
            role=OrganizationRole(invitation.role),
            email=invitation.email,
        )


@invitations_router.post("/accept")
async def accept_invitation_endpoint(
    body: AcceptInvitationRequest,
    app_state: AppState = Depends(get_app_state),
    user: AuthenticatedUser = Depends(require_session),
) -> MembershipOut:
    lookup_hash = hash_token(body.token)
    async with token_lookup_session(app_state.session_factory, lookup_hash) as lookup_session:
        org_repo = OrganizationsRepository(lookup_session)
        invitation = await resolve_invitation_by_token(org_repo, raw_token=body.token)
        organization_id = invitation.organization_id
        invitation_id = invitation.id

    tenant = TenantContext(organization_id=organization_id, actor_user_id=user.id)
    async with tenant_session(app_state.session_factory, tenant) as session:
        org_repo = OrganizationsRepository(session)
        fresh_invitation = await org_repo.get_invitation(
            organization_id, invitation_id, for_update=True
        )
        if fresh_invitation is None:
            raise NotFoundError("This invitation is invalid or has expired.")
        membership = await accept_invitation(
            org_repo,
            invitation=fresh_invitation,
            accepting_user_id=user.id,
            accepting_user_email=user.email,
        )
        await record_audit(
            session,
            organization_id=organization_id,
            action="member.invitation_accepted",
            summary="Accepted an organization invitation",
            actor_type=ActorType.USER,
            actor_user_id=user.id,
            actor_label=user.full_name,
            resource_type="organization_membership",
            resource_id=membership.id,
        )
    return MembershipOut.model_validate(membership)
