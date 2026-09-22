"""RBAC roles and permissions. See docs/architecture/02-multi-tenancy.md §3.

Roles are ranked and inclusive: a permission granted to a role is granted
to every role ranked above it. `Permission` is checked against a role's
rank, not against the role directly, so adding a permission is a
one-line addition to `PERMISSION_MIN_RANK`, never a new branch of
if/elif per role.
"""

from enum import StrEnum


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


ROLE_RANK: dict[OrganizationRole, int] = {
    OrganizationRole.MEMBER: 10,
    OrganizationRole.MANAGER: 20,
    OrganizationRole.ADMIN: 30,
    OrganizationRole.OWNER: 40,
}


class Permission(StrEnum):
    ORG_READ = "org.read"
    ORG_SETTINGS_WRITE = "org.settings.write"
    ORG_DELETE = "org.delete"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    OWNERSHIP_TRANSFER = "ownership.transfer"
    INVITATIONS_MANAGE = "invitations.manage"
    AUDIT_READ = "audit.read"
    BILLING_MANAGE = "billing.manage"
    IMPORTS_READ = "imports.read"
    IMPORTS_MANAGE = "imports.manage"
    REWORK_READ = "rework.read"
    REWORK_REVIEW = "rework.review"


# See docs/architecture/02-multi-tenancy.md §3's permission matrix.
PERMISSION_MIN_RANK: dict[Permission, int] = {
    Permission.ORG_READ: ROLE_RANK[OrganizationRole.MEMBER],
    Permission.ORG_SETTINGS_WRITE: ROLE_RANK[OrganizationRole.ADMIN],
    Permission.ORG_DELETE: ROLE_RANK[OrganizationRole.OWNER],
    Permission.MEMBERS_READ: ROLE_RANK[OrganizationRole.MEMBER],
    Permission.MEMBERS_MANAGE: ROLE_RANK[OrganizationRole.ADMIN],
    Permission.OWNERSHIP_TRANSFER: ROLE_RANK[OrganizationRole.OWNER],
    Permission.INVITATIONS_MANAGE: ROLE_RANK[OrganizationRole.ADMIN],
    Permission.AUDIT_READ: ROLE_RANK[OrganizationRole.ADMIN],
    Permission.BILLING_MANAGE: ROLE_RANK[OrganizationRole.OWNER],
    Permission.IMPORTS_READ: ROLE_RANK[OrganizationRole.MEMBER],
    Permission.IMPORTS_MANAGE: ROLE_RANK[OrganizationRole.MANAGER],
    Permission.REWORK_READ: ROLE_RANK[OrganizationRole.MEMBER],
    Permission.REWORK_REVIEW: ROLE_RANK[OrganizationRole.MANAGER],
}


def role_has_permission(role: OrganizationRole | None, permission: Permission) -> bool:
    """`role=None` is a system actor — see CLAUDE.md rule 5. Background
    jobs bypass permission checks (they had their authorization decided
    at enqueue time); this function is only ever called at the API
    boundary, where `role` is never None for a human request."""
    if role is None:
        return True
    return ROLE_RANK[role] >= PERMISSION_MIN_RANK[permission]
