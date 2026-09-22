"""Organizations repository.

`Organization` has no RLS (it's the tenant, not tenant-owned). Membership
and invitation queries rely on the dual-clause RLS policies described in
migrations/rls_helpers.py — this repository does not re-implement that
scoping itself; it trusts the database to enforce it, and just needs to
be called through the right session (tenant_session / user_session /
token_lookup_session) for a given method to see what it expects to see.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import (
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
)


class OrganizationsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- organizations -----------------------------------------------------

    async def set_organization_context(self, organization_id: UUID) -> None:
        """Set the transaction-local org after creating a new tenant.

        Organization creation starts in a user-scoped transaction because no
        organization exists yet. The owner membership is tenant-owned, so the
        new org must become the RLS context before that membership is inserted.
        """
        await self._session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(organization_id)},
        )

    async def get_organization(self, organization_id: UUID) -> Organization | None:
        result = await self._session.execute(
            select(Organization).where(Organization.id == organization_id)
        )
        return result.scalar_one_or_none()

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def create_organization(
        self, *, name: str, slug: str, created_by_user_id: UUID
    ) -> Organization:
        org = Organization(name=name, slug=slug, created_by_user_id=created_by_user_id)
        self._session.add(org)
        await self._session.flush()
        return org

    # --- memberships --------------------------------------------------------
    # Reads here rely on organization_memberships' dual RLS policy — see
    # this module's docstring.

    async def list_my_memberships(self) -> list[OrganizationMembership]:
        """Requires a `user_session` (sets app.current_user_id) — RLS's
        self-access clause is what makes this return rows across every
        org the caller belongs to, without an org_id in scope at all."""
        result = await self._session.execute(
            select(OrganizationMembership).where(OrganizationMembership.revoked_at.is_(None))
        )
        return list(result.scalars().all())

    async def get_active_membership(
        self, organization_id: UUID, user_id: UUID
    ) -> OrganizationMembership | None:
        result = await self._session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.user_id == user_id,
                OrganizationMembership.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_active_members(self, organization_id: UUID) -> list[OrganizationMembership]:
        result = await self._session.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.revoked_at.is_(None),
            )
            .order_by(OrganizationMembership.joined_at)
        )
        return list(result.scalars().all())

    async def count_active_owners(self, organization_id: UUID) -> int:
        rows = await self.list_active_members(organization_id)
        return sum(1 for m in rows if m.role == "owner")

    async def create_membership(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role: str,
        invited_by_user_id: UUID | None,
    ) -> OrganizationMembership:
        membership = OrganizationMembership(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            invited_by_user_id=invited_by_user_id,
        )
        self._session.add(membership)
        await self._session.flush()
        return membership

    # --- invitations ---------------------------------------------------------

    async def get_invitation_by_token(self, token_hash: str) -> OrganizationInvitation | None:
        """Requires a `token_lookup_session` — see this module's
        docstring and db/session.py."""
        result = await self._session.execute(
            select(OrganizationInvitation).where(OrganizationInvitation.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def get_pending_invitation(
        self, organization_id: UUID, email: str
    ) -> OrganizationInvitation | None:
        result = await self._session.execute(
            select(OrganizationInvitation).where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.email == email,
                OrganizationInvitation.accepted_at.is_(None),
                OrganizationInvitation.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def list_pending_invitations(self, organization_id: UUID) -> list[OrganizationInvitation]:
        result = await self._session.execute(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.organization_id == organization_id,
                OrganizationInvitation.accepted_at.is_(None),
                OrganizationInvitation.revoked_at.is_(None),
            )
            .order_by(OrganizationInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_invitations_for_email(self, email: str) -> list[OrganizationInvitation]:
        result = await self._session.execute(
            select(OrganizationInvitation)
            .where(
                OrganizationInvitation.email == email,
                OrganizationInvitation.accepted_at.is_(None),
                OrganizationInvitation.revoked_at.is_(None),
            )
            .order_by(OrganizationInvitation.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_invitation(
        self,
        *,
        organization_id: UUID,
        email: str,
        role: str,
        token_hash: str,
        invited_by_user_id: UUID,
        expires_at: datetime,
    ) -> OrganizationInvitation:
        invitation = OrganizationInvitation(
            organization_id=organization_id,
            email=email,
            role=role,
            token_hash=token_hash,
            invited_by_user_id=invited_by_user_id,
            expires_at=expires_at,
        )
        self._session.add(invitation)
        await self._session.flush()
        return invitation

    async def get_invitation(
        self, organization_id: UUID, invitation_id: UUID, *, for_update: bool = False
    ) -> OrganizationInvitation | None:
        statement = select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.id == invitation_id,
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()
