"""Tenant isolation tests.

Mission section 6: "No request may access another tenant's resources."

These are the tests that decide whether this system can ever hold real
customer data. Each one is written as an ATTACK — it does the thing an
attacker would do and asserts it fails. A test that only checks the happy path
proves nothing about isolation.

Every test here uses two REAL workspaces created through the public signup
endpoint. No fixture reaches into the database to fabricate a state that the
API itself would not produce.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from kynd_api.main import create_app
from kynd_api.models import Membership, Role, User, Workspace


@pytest.fixture
def tenant_a(client):
    """Workspace A, its OWNER, and an authenticated client."""
    body = client.post(
        "/auth/signup",
        json={
            "email": "owner-a@acme-isolation.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Acme",
            "name": "Owner A",
        },
    )
    # Assert the fixture's own setup succeeded. Without this a rejected signup
    # returns a validation body and every test downstream fails with an opaque
    # KeyError instead of naming the real cause.
    assert body.status_code == 201, f"tenant A signup failed: {body.text}"
    return {"client": client, **body.json()}


@pytest.fixture
def tenant_b():
    """Workspace B on a SEPARATE client, so the two never share a cookie jar."""
    with TestClient(create_app()) as other:
        body = other.post(
            "/auth/signup",
            json={
                "email": "owner-b@globex-isolation.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Globex",
                "name": "Owner B",
            },
        )
        assert body.status_code == 201, f"tenant B signup failed: {body.text}"
        yield {"client": other, **body.json()}


class TestWorkspaceIsolation:
    def test_two_signups_produce_genuinely_separate_workspaces(self, tenant_a, tenant_b):
        assert tenant_a["workspace"]["id"] != tenant_b["workspace"]["id"]
        assert tenant_a["user"]["id"] != tenant_b["user"]["id"]

    def test_a_cannot_read_b_workspace_via_header(self, tenant_a, tenant_b):
        """The core attack: name another tenant's workspace in the header."""
        response = tenant_a["client"].get(
            "/workspace",
            headers={"X-Kynd-Workspace": tenant_b["workspace"]["id"]},
        )
        assert response.status_code == 404, (
            "tenant A read tenant B's workspace by asking for it"
        )

    def test_a_cannot_list_b_members(self, tenant_a, tenant_b):
        response = tenant_a["client"].get(
            "/workspace/members",
            headers={"X-Kynd-Workspace": tenant_b["workspace"]["id"]},
        )
        assert response.status_code == 404

    def test_a_cannot_update_b_workspace(self, tenant_a, tenant_b):
        response = tenant_a["client"].patch(
            "/workspace",
            json={"name": "Owned By A Now"},
            headers={"X-Kynd-Workspace": tenant_b["workspace"]["id"]},
        )
        assert response.status_code == 404

        # And B is genuinely unchanged — a 404 that still wrote would be worse
        # than a 200 that did not.
        after = tenant_b["client"].get("/workspace").json()
        assert after["name"] == "Globex"

    def test_cross_tenant_denial_is_404_not_403(self, tenant_a, tenant_b):
        """404, so the response cannot be used to enumerate real workspace ids.

        A 403 for a real-but-foreign id and 404 for a nonexistent one tells an
        attacker exactly which ids exist.
        """
        real_foreign = tenant_a["client"].get(
            "/workspace", headers={"X-Kynd-Workspace": tenant_b["workspace"]["id"]}
        )
        pure_fiction = tenant_a["client"].get(
            "/workspace", headers={"X-Kynd-Workspace": "ws_0000000000000000000000000000"}
        )
        assert real_foreign.status_code == pure_fiction.status_code == 404
        assert real_foreign.json() == pure_fiction.json()

    def test_me_lists_only_the_callers_own_workspaces(self, tenant_a, tenant_b):
        body = tenant_a["client"].get("/auth/me").json()
        ids = {workspace["id"] for workspace in body["workspaces"]}
        assert ids == {tenant_a["workspace"]["id"]}
        assert tenant_b["workspace"]["id"] not in ids

    def test_members_list_never_contains_another_tenants_users(self, tenant_a, tenant_b):
        members = tenant_a["client"].get("/workspace/members").json()
        emails = {member["email"] for member in members}
        assert emails == {"owner-a@acme-isolation.com"}
        assert "owner-b@globex-isolation.com" not in emails


class TestMembershipIdorIsolation:
    """Direct object references to another tenant's membership rows."""

    def test_a_cannot_change_a_role_in_b(self, tenant_a, tenant_b, db):
        b_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == tenant_b["workspace"]["id"]
            )
        ).scalar_one()

        response = tenant_a["client"].patch(
            f"/workspace/members/{b_membership.id}",
            json={"role": "VIEWER"},
        )
        assert response.status_code == 404, "tenant A demoted tenant B's owner"

        db.expire_all()
        unchanged = db.get(Membership, b_membership.id)
        assert unchanged.role == Role.OWNER

    def test_a_cannot_remove_a_member_of_b(self, tenant_a, tenant_b, db):
        b_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == tenant_b["workspace"]["id"]
            )
        ).scalar_one()

        response = tenant_a["client"].delete(f"/workspace/members/{b_membership.id}")
        assert response.status_code == 404

        db.expire_all()
        assert db.get(Membership, b_membership.id) is not None
        # B can still use their workspace afterwards.
        assert tenant_b["client"].get("/workspace").status_code == 200

    def test_a_cannot_remove_b_member_even_while_naming_b_workspace(
        self, tenant_a, tenant_b, db
    ):
        """Header AND object id both point at B. Both checks must hold."""
        b_membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == tenant_b["workspace"]["id"]
            )
        ).scalar_one()

        response = tenant_a["client"].delete(
            f"/workspace/members/{b_membership.id}",
            headers={"X-Kynd-Workspace": tenant_b["workspace"]["id"]},
        )
        assert response.status_code == 404

        db.expire_all()
        assert db.get(Membership, b_membership.id) is not None


class TestSessionIsolation:
    def test_b_session_cookie_does_not_authenticate_as_a(self, tenant_a, tenant_b):
        """A stolen cookie authenticates as its OWNER, never as someone else."""
        b_cookie = tenant_b["client"].cookies.get("kynd_session")

        with TestClient(create_app()) as attacker:
            attacker.cookies.set("kynd_session", b_cookie)
            body = attacker.get("/auth/me").json()

        assert body["user"]["email"] == "owner-b@globex-isolation.com"
        assert body["workspaces"][0]["id"] == tenant_b["workspace"]["id"]

    def test_a_logout_does_not_affect_b(self, tenant_a, tenant_b):
        tenant_a["client"].post("/auth/logout")
        assert tenant_a["client"].get("/auth/me").status_code == 401
        assert tenant_b["client"].get("/auth/me").status_code == 200

    def test_unauthenticated_requests_reach_nothing(self, tenant_a):
        with TestClient(create_app()) as anonymous:
            for method, path in [
                ("get", "/auth/me"),
                ("get", "/workspace"),
                ("get", "/workspace/members"),
                ("patch", "/workspace"),
            ]:
                response = getattr(anonymous, method)(
                    path, **({"json": {}} if method == "patch" else {})
                )
                assert response.status_code == 401, f"{method.upper()} {path} was open"


class TestNoTenantIdFromClient:
    """The client must never be able to assert a tenant identity."""

    def test_workspace_id_in_a_request_body_is_ignored(self, tenant_a, tenant_b):
        response = tenant_a["client"].patch(
            "/workspace",
            json={
                "name": "Renamed",
                # A body field an attacker would try, hoping it is trusted.
                "workspace_id": tenant_b["workspace"]["id"],
                "id": tenant_b["workspace"]["id"],
            },
        )
        assert response.status_code == 200
        # A's own workspace was renamed. B's was not touched.
        assert response.json()["id"] == tenant_a["workspace"]["id"]
        assert tenant_b["client"].get("/workspace").json()["name"] == "Globex"

    def test_a_user_with_no_membership_is_refused(self, client, db):
        """Authentication is not authorization: a valid session with no
        membership must not fall through to some default workspace."""
        signup = client.post(
            "/auth/signup",
            json={
                "email": "orphan@nowhere-isolation.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Doomed",
            },
        ).json()

        membership = db.execute(
            select(Membership).where(
                Membership.workspace_id == signup["workspace"]["id"]
            )
        ).scalar_one()
        db.delete(membership)
        db.commit()

        assert client.get("/workspace").status_code == 403
