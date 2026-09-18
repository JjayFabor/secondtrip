"""RBAC roles. See docs/architecture/02-multi-tenancy.md §3.

Only `OrganizationRole` exists in Phase 2 — `TenantContext` needs it to
type-check. The `Permission` enum, the rank map, and `require_permission`
arrive in PLAN.md Step 3 alongside the API routes they gate.
"""

from enum import StrEnum


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


# Rank order — a permission granted to a role is granted to every role
# ranked above it. See 02 §3.
ROLE_RANK: dict[OrganizationRole, int] = {
    OrganizationRole.MEMBER: 10,
    OrganizationRole.MANAGER: 20,
    OrganizationRole.ADMIN: 30,
    OrganizationRole.OWNER: 40,
}
