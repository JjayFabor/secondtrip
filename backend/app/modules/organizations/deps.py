"""Organizations' dependency helpers — "which org, what role", built on
top of identity's "who is the caller". A module depending on another
module's public surface (never its repository/models) is the allowed
direction — see docs/architecture/01-system-architecture.md §5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from fastapi import Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition import AppState, get_app_state
from app.core.errors import ForbiddenError, NotFoundError
from app.core.permissions import OrganizationRole, Permission, role_has_permission
from app.core.tenancy import TenantContext
from app.db.session import tenant_session
from app.modules.identity.deps import AuthenticatedUser, require_session
from app.modules.organizations.repository import OrganizationsRepository


async def require_org_context(
    request: Request,
    org_id: UUID = Path(...),
    user: AuthenticatedUser = Depends(require_session),
    app_state: AppState = Depends(get_app_state),
) -> TenantContext:
    """Path org_id -> membership check -> TenantContext, or 404 — never
    403, which would confirm the org exists to a user who isn't a member
    of it. See docs/architecture/02-multi-tenancy.md §2 layer 3."""
    request_id = getattr(request.state, "request_id", None)
    tenant = TenantContext(organization_id=org_id, actor_user_id=user.id, request_id=request_id)
    async with tenant_session(app_state.session_factory, tenant) as session:
        org_repo = OrganizationsRepository(session)
        membership = await org_repo.get_active_membership(org_id, user.id)
        if membership is None:
            raise NotFoundError("Organization not found.")
        return TenantContext(
            organization_id=org_id,
            actor_user_id=user.id,
            role=OrganizationRole(membership.role),
            request_id=request_id,
        )


def require_permission(permission: Permission) -> Callable[..., Awaitable[TenantContext]]:
    """Returns a FastAPI dependency callable, not a plain function of
    `TenantContext` — its own `tenant` parameter is itself resolved by
    `Depends(require_org_context)`, which is why the signature here is
    `Callable[..., Awaitable[TenantContext]]` rather than
    `Callable[[TenantContext], TenantContext]`: nothing in this codebase
    ever calls `_check` directly with a `TenantContext` argument."""

    async def _check(tenant: TenantContext = Depends(require_org_context)) -> TenantContext:
        if not role_has_permission(tenant.role, permission):
            raise ForbiddenError("You don't have permission to do that.")
        return tenant

    return _check


async def get_tenant_session(
    org_id: UUID = Path(...),
    tenant: TenantContext = Depends(require_org_context),
    app_state: AppState = Depends(get_app_state),
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(app_state.session_factory, tenant) as session:
        yield session
