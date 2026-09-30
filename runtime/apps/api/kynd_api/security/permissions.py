"""The permission matrix.

Permissions are DATA, in one table, in one file. The alternative — a role check
written inline at each endpoint — is how authorization bugs happen: the matrix
becomes unreviewable, and nobody can answer "what exactly can an OPERATOR do?"
without grepping the whole codebase.

Adding an endpoint means adding a Permission here and naming it in the route's
dependency. There is no default-allow.
"""

from __future__ import annotations

import enum

from ..models import Role


class Permission(str, enum.Enum):
    """Every distinct authority in the product."""

    # Workspace
    WORKSPACE_READ = "workspace:read"
    WORKSPACE_UPDATE = "workspace:update"
    WORKSPACE_DELETE = "workspace:delete"

    # Team
    MEMBER_READ = "member:read"
    MEMBER_INVITE = "member:invite"
    MEMBER_UPDATE_ROLE = "member:update_role"
    MEMBER_REMOVE = "member:remove"

    # Integrations
    INTEGRATION_READ = "integration:read"
    INTEGRATION_CONNECT = "integration:connect"
    INTEGRATION_DISCONNECT = "integration:disconnect"
    INTEGRATION_TEST = "integration:test"

    # Governance
    GOVERNANCE_READ = "governance:read"
    GOVERNANCE_UPDATE = "governance:update"

    # Actions and approvals
    ACTION_PROPOSE = "action:propose"
    ACTION_EXECUTE = "action:execute"
    APPROVAL_READ = "approval:read"
    APPROVAL_DECIDE = "approval:decide"

    # History
    EXECUTION_READ = "execution:read"
    AUDIT_READ = "audit:read"

    # Commercial
    USAGE_READ = "usage:read"
    BILLING_READ = "billing:read"
    BILLING_MANAGE = "billing:manage"

    # API access
    APIKEY_READ = "apikey:read"
    APIKEY_CREATE = "apikey:create"
    APIKEY_REVOKE = "apikey:revoke"


# Read-only baseline. Everyone in a workspace can see what Kynd is doing —
# governance is only useful if it is visible.
_VIEWER: frozenset[Permission] = frozenset(
    {
        Permission.WORKSPACE_READ,
        Permission.MEMBER_READ,
        Permission.INTEGRATION_READ,
        Permission.GOVERNANCE_READ,
        Permission.APPROVAL_READ,
        Permission.EXECUTION_READ,
        Permission.AUDIT_READ,
        Permission.USAGE_READ,
    }
)

# Can make things happen inside the rules, and can approve. Cannot change what
# the rules ARE — that separation is the point: an OPERATOR who could edit
# governance could simply delete the rule blocking them.
_OPERATOR: frozenset[Permission] = _VIEWER | {
    Permission.ACTION_PROPOSE,
    Permission.ACTION_EXECUTE,
    Permission.APPROVAL_DECIDE,
    Permission.INTEGRATION_TEST,
}

# Configures the workspace: integrations, governance, team, and can see billing.
_ADMIN: frozenset[Permission] = _OPERATOR | {
    Permission.WORKSPACE_UPDATE,
    Permission.MEMBER_INVITE,
    Permission.MEMBER_UPDATE_ROLE,
    Permission.MEMBER_REMOVE,
    Permission.INTEGRATION_CONNECT,
    Permission.INTEGRATION_DISCONNECT,
    Permission.GOVERNANCE_UPDATE,
    Permission.BILLING_READ,
    Permission.APIKEY_READ,
    Permission.APIKEY_CREATE,
    Permission.APIKEY_REVOKE,
}

# Everything, including destroying the workspace and changing what is paid.
_OWNER: frozenset[Permission] = _ADMIN | {
    Permission.WORKSPACE_DELETE,
    Permission.BILLING_MANAGE,
}


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: _VIEWER,
    Role.OPERATOR: _OPERATOR,
    Role.ADMIN: _ADMIN,
    Role.OWNER: _OWNER,
}


def role_has_permission(role: Role, permission: Permission) -> bool:
    """Whether `role` may do `permission`. Unknown role denies (fail closed)."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def permissions_for_role(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())


def assert_matrix_is_monotonic() -> None:
    """Every role must be a strict superset of the one below it.

    Called by a test. A non-monotonic matrix (an OPERATOR who can do something
    an ADMIN cannot) is almost always an editing mistake rather than a design
    decision, and it produces support tickets nobody can reproduce.
    """
    order = [Role.VIEWER, Role.OPERATOR, Role.ADMIN, Role.OWNER]
    for lower, higher in zip(order, order[1:]):
        missing = ROLE_PERMISSIONS[lower] - ROLE_PERMISSIONS[higher]
        if missing:
            raise AssertionError(
                f"{higher.value} is missing permissions held by {lower.value}: "
                f"{sorted(p.value for p in missing)}"
            )
