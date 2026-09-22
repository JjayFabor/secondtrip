from app.core.permissions import OrganizationRole, Permission, role_has_permission


def test_permission_matrix_is_ranked_and_inclusive() -> None:
    expected_minimum_roles = {
        Permission.ORG_READ: OrganizationRole.MEMBER,
        Permission.ORG_SETTINGS_WRITE: OrganizationRole.ADMIN,
        Permission.ORG_DELETE: OrganizationRole.OWNER,
        Permission.MEMBERS_READ: OrganizationRole.MEMBER,
        Permission.MEMBERS_MANAGE: OrganizationRole.ADMIN,
        Permission.OWNERSHIP_TRANSFER: OrganizationRole.OWNER,
        Permission.INVITATIONS_MANAGE: OrganizationRole.ADMIN,
        Permission.AUDIT_READ: OrganizationRole.ADMIN,
        Permission.BILLING_MANAGE: OrganizationRole.OWNER,
        Permission.IMPORTS_READ: OrganizationRole.MEMBER,
        Permission.IMPORTS_MANAGE: OrganizationRole.MANAGER,
        Permission.REWORK_READ: OrganizationRole.MEMBER,
        Permission.REWORK_REVIEW: OrganizationRole.MANAGER,
    }
    role_order = [
        OrganizationRole.MEMBER,
        OrganizationRole.MANAGER,
        OrganizationRole.ADMIN,
        OrganizationRole.OWNER,
    ]

    for permission, minimum_role in expected_minimum_roles.items():
        minimum_index = role_order.index(minimum_role)
        for index, role in enumerate(role_order):
            assert role_has_permission(role, permission) is (index >= minimum_index)
