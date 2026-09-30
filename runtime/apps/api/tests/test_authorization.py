"""Authorization tests.

Mission section 8: "Do not assume authentication means authorization. Test
every sensitive endpoint."

Authentication proves who you are. These tests prove that being *someone* is
not the same as being allowed. Each sensitive endpoint is exercised by all
four roles, and the expected outcome is stated per role rather than inferred.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from kynd_api.main import create_app
from kynd_api.models import Membership, Role, User
from kynd_api.security.permissions import (
    Permission,
    ROLE_PERMISSIONS,
    assert_matrix_is_monotonic,
    role_has_permission,
)

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def workspace_with_all_roles(client, db):
    """One workspace containing an OWNER, ADMIN, OPERATOR, and VIEWER.

    Members are created by direct insert because there is no invite endpoint
    yet. The AUTHORIZATION path under test is unaffected — each member still
    logs in through the real endpoint and is resolved by the real dependency.
    """
    owner = client.post(
        "/auth/signup",
        json={
            "email": "owner@rolestest.com",
            "password": PASSWORD,
            "workspace_name": "Roles Inc",
            "name": "Owner",
        },
    )
    assert owner.status_code == 201, owner.text
    workspace_id = owner.json()["workspace"]["id"]

    from kynd_api.security.passwords import hash_password

    clients: dict[Role, TestClient] = {}
    for role in (Role.ADMIN, Role.OPERATOR, Role.VIEWER):
        email = f"{role.value.lower()}@rolestest.com"
        user = User(
            email=email,
            email_normalized=email,
            password_hash=hash_password(PASSWORD),
            name=role.value.title(),
        )
        db.add(user)
        db.flush()
        db.add(Membership(user_id=user.id, workspace_id=workspace_id, role=role))
    db.commit()

    for role in (Role.ADMIN, Role.OPERATOR, Role.VIEWER):
        member_client = TestClient(create_app())
        response = member_client.post(
            "/auth/login",
            json={"email": f"{role.value.lower()}@rolestest.com", "password": PASSWORD},
        )
        assert response.status_code == 200, response.text
        clients[role] = member_client

    clients[Role.OWNER] = client

    yield {"workspace_id": workspace_id, "clients": clients}

    for role, member_client in clients.items():
        if role != Role.OWNER:
            member_client.close()


class TestPermissionMatrix:
    def test_matrix_is_monotonic(self):
        """Each role must include everything the role below it can do."""
        assert_matrix_is_monotonic()

    def test_viewer_cannot_change_anything(self):
        viewer = ROLE_PERMISSIONS[Role.VIEWER]
        for permission in viewer:
            assert permission.value.split(":")[1] in {
                "read",
            }, f"VIEWER holds a non-read permission: {permission.value}"

    def test_operator_cannot_edit_governance(self):
        """The separation that makes governance meaningful.

        An OPERATOR who could edit the rules could delete the rule that blocks
        them, which would make every other control decorative.
        """
        assert not role_has_permission(Role.OPERATOR, Permission.GOVERNANCE_UPDATE)
        assert role_has_permission(Role.OPERATOR, Permission.GOVERNANCE_READ)

    def test_operator_cannot_manage_integrations_or_team(self):
        for permission in (
            Permission.INTEGRATION_CONNECT,
            Permission.INTEGRATION_DISCONNECT,
            Permission.MEMBER_INVITE,
            Permission.MEMBER_REMOVE,
        ):
            assert not role_has_permission(Role.OPERATOR, permission)

    def test_admin_cannot_manage_billing_or_delete_workspace(self):
        assert not role_has_permission(Role.ADMIN, Permission.BILLING_MANAGE)
        assert not role_has_permission(Role.ADMIN, Permission.WORKSPACE_DELETE)
        assert role_has_permission(Role.ADMIN, Permission.BILLING_READ)

    def test_owner_holds_every_permission(self):
        assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission)

    def test_unknown_role_denies_everything(self):
        """Fail closed: an unrecognised role grants nothing."""
        assert not role_has_permission("SUPERUSER", Permission.WORKSPACE_READ)  # type: ignore[arg-type]


class TestEndpointAuthorization:
    """Every role against every sensitive endpoint."""

    def test_all_roles_can_read_the_workspace(self, workspace_with_all_roles):
        for role, member_client in workspace_with_all_roles["clients"].items():
            response = member_client.get("/workspace")
            assert response.status_code == 200, f"{role.value} could not read"

    def test_all_roles_can_read_members(self, workspace_with_all_roles):
        for role, member_client in workspace_with_all_roles["clients"].items():
            response = member_client.get("/workspace/members")
            assert response.status_code == 200, f"{role.value} could not list members"

    @pytest.mark.parametrize(
        "role,expected",
        [(Role.OWNER, 200), (Role.ADMIN, 200), (Role.OPERATOR, 403), (Role.VIEWER, 403)],
    )
    def test_workspace_update_requires_admin(
        self, workspace_with_all_roles, role, expected
    ):
        response = workspace_with_all_roles["clients"][role].patch(
            "/workspace", json={"name": f"Renamed by {role.value}"}
        )
        assert response.status_code == expected, (
            f"{role.value} PATCH /workspace returned {response.status_code}, "
            f"expected {expected}"
        )

    @pytest.mark.parametrize(
        "role,expected",
        [(Role.OWNER, 200), (Role.ADMIN, 200), (Role.OPERATOR, 403), (Role.VIEWER, 403)],
    )
    def test_complete_onboarding_requires_admin(
        self, workspace_with_all_roles, role, expected
    ):
        response = workspace_with_all_roles["clients"][role].post(
            "/workspace/complete-onboarding"
        )
        assert response.status_code == expected

    @pytest.mark.parametrize(
        "role,expected",
        [(Role.OWNER, 404), (Role.ADMIN, 404), (Role.OPERATOR, 403), (Role.VIEWER, 403)],
    )
    def test_member_removal_requires_admin(
        self, workspace_with_all_roles, role, expected
    ):
        """404 for permitted roles = authorized but the target does not exist.

        The distinction matters: an unauthorized role must be stopped BEFORE
        the object is looked up, otherwise the response tells them whether a
        membership id exists.
        """
        response = workspace_with_all_roles["clients"][role].delete(
            "/workspace/members/mem_does_not_exist"
        )
        assert response.status_code == expected

    def test_authorization_is_checked_before_object_lookup(
        self, workspace_with_all_roles, db
    ):
        """A VIEWER gets 403 for a REAL membership id, not 404.

        If the handler looked the object up first, a VIEWER could distinguish
        real ids from fake ones by the status code alone.
        """
        real_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.VIEWER,
            )
        ).scalar_one()

        viewer = workspace_with_all_roles["clients"][Role.VIEWER]
        real = viewer.delete(f"/workspace/members/{real_membership.id}")
        fake = viewer.delete("/workspace/members/mem_totally_made_up")

        assert real.status_code == fake.status_code == 403


class TestPrivilegeEscalation:
    def test_admin_cannot_grant_owner(self, workspace_with_all_roles, db):
        """An ADMIN who could mint OWNERs could promote themselves."""
        admin_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.ADMIN,
            )
        ).scalar_one()

        response = workspace_with_all_roles["clients"][Role.ADMIN].patch(
            f"/workspace/members/{admin_membership.id}", json={"role": "OWNER"}
        )
        assert response.status_code == 403

        db.expire_all()
        assert db.get(Membership, admin_membership.id).role == Role.ADMIN

    def test_viewer_cannot_promote_themselves(self, workspace_with_all_roles, db):
        viewer_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.VIEWER,
            )
        ).scalar_one()

        response = workspace_with_all_roles["clients"][Role.VIEWER].patch(
            f"/workspace/members/{viewer_membership.id}", json={"role": "OWNER"}
        )
        assert response.status_code == 403

        db.expire_all()
        assert db.get(Membership, viewer_membership.id).role == Role.VIEWER

    def test_owner_can_grant_owner(self, workspace_with_all_roles, db):
        admin_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.ADMIN,
            )
        ).scalar_one()

        response = workspace_with_all_roles["clients"][Role.OWNER].patch(
            f"/workspace/members/{admin_membership.id}", json={"role": "OWNER"}
        )
        assert response.status_code == 200
        assert response.json()["role"] == "OWNER"

    def test_last_owner_cannot_be_demoted(self, workspace_with_all_roles, db):
        """A workspace with no OWNER cannot be administered or cancelled."""
        owner_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.OWNER,
            )
        ).scalar_one()

        response = workspace_with_all_roles["clients"][Role.OWNER].patch(
            f"/workspace/members/{owner_membership.id}", json={"role": "VIEWER"}
        )
        assert response.status_code == 409

        db.expire_all()
        assert db.get(Membership, owner_membership.id).role == Role.OWNER

    def test_last_owner_cannot_be_removed(self, workspace_with_all_roles, db):
        owner_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.OWNER,
            )
        ).scalar_one()

        response = workspace_with_all_roles["clients"][Role.OWNER].delete(
            f"/workspace/members/{owner_membership.id}"
        )
        assert response.status_code == 409

    def test_invalid_role_value_is_rejected(self, workspace_with_all_roles, db):
        membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_with_all_roles["workspace_id"],
                Membership.role == Role.VIEWER,
            )
        ).scalar_one()

        for bogus in ["SUPERUSER", "owner", "", None, 123]:
            response = workspace_with_all_roles["clients"][Role.OWNER].patch(
                f"/workspace/members/{membership.id}", json={"role": bogus}
            )
            assert response.status_code == 422, f"accepted bogus role {bogus!r}"


class TestPermissionsReportedToTheUi:
    """The UI renders from /auth/me permissions, so it must match enforcement."""

    def test_reported_permissions_match_the_matrix(self, workspace_with_all_roles):
        for role, member_client in workspace_with_all_roles["clients"].items():
            reported = set(member_client.get("/auth/me").json()["permissions"])
            expected = {p.value for p in ROLE_PERMISSIONS[role]}
            assert reported == expected, f"{role.value} sees the wrong permission list"

    def test_viewer_is_not_told_they_can_write(self, workspace_with_all_roles):
        permissions = (
            workspace_with_all_roles["clients"][Role.VIEWER]
            .get("/auth/me")
            .json()["permissions"]
        )
        assert "governance:update" not in permissions
        assert "workspace:update" not in permissions
