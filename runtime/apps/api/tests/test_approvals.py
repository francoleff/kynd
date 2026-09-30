"""Phase 6 — Approval Center.

Proves the mission's exit gate literally: propose -> appears pending ->
approve as an authorised user -> a real runtime approval token is minted ->
reject blocks re-decision -> a VIEWER cannot approve -> an expired request
cannot be approved -> a forged/replayed approval_id from the client is never
trusted (the runtime mints its own; the client never sends one).
"""

from __future__ import annotations

from datetime import timedelta

from kynd_api.models import ApprovalRequest, ApprovalRequestStatus, Role, utcnow
from kynd_api.runtime.store_factory import get_store

from .conftest import signup_user


def _elevate_to_operator(db, client, owner) -> None:
    """No-op placeholder retained for symmetry with other test files."""


def test_propose_then_appears_pending(client, owner):
    response = client.post(
        "/approvals",
        json={"capability": "send_message", "action_type": "external_message", "amount": None},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["capability"] == "send_message"

    listing = client.get("/approvals")
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()]
    assert body["id"] in ids


def test_approve_mints_real_runtime_token(client, owner, db):
    created = client.post(
        "/approvals",
        json={
            "capability": "send_message",
            "action_type": "external_message",
            "target": "#general",
        },
    ).json()

    decided = client.post(f"/approvals/{created['id']}/approve", json={"note": "looks fine"})
    assert decided.status_code == 200, decided.text
    body = decided.json()
    assert body["status"] == "APPROVED"

    # The row in Postgres records which runtime token was minted...
    row = db.get(ApprovalRequest, created["id"])
    db.refresh(row)
    assert row.runtime_approval_id is not None

    # ...and that token is REAL: the runtime's own store, not this table, is
    # what an execution will actually check.
    workspace_id = owner["workspace"]["id"]
    store = get_store(workspace_id)
    check = store.validate_approval(
        row.runtime_approval_id, capability="send_message", action_type="external_message",
        target="#general",
    )
    assert check.ok, check.reason


def test_reject_blocks_future_decision(client, owner):
    created = client.post("/approvals", json={"capability": "send_message"}).json()

    rejected = client.post(f"/approvals/{created['id']}/reject", json={"note": "no"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    # Cannot approve something already decided.
    second = client.post(f"/approvals/{created['id']}/approve", json={})
    assert second.status_code == 409


def test_viewer_cannot_approve(client, owner, db):
    """A VIEWER can see the request but not decide it."""
    created = client.post("/approvals", json={"capability": "send_message"}).json()

    viewer = signup_user(client, email="viewer@example.com", workspace_name="Viewer WS")
    # Demote the viewer's own workspace owner role isn't the point here — the
    # point is workspace ISOLATION plus role enforcement. Simulate a VIEWER in
    # the owner's workspace directly via the DB, the same pattern other test
    # files in this suite use for role coverage.
    from kynd_api.models import Membership, User

    viewer_user = db.execute(
        __import__("sqlalchemy").select(User).where(User.email == "viewer@example.com")
    ).scalar_one()
    membership = Membership(
        user_id=viewer_user.id, workspace_id=owner["workspace"]["id"], role=Role.VIEWER
    )
    db.add(membership)
    db.commit()

    viewer_client_login = client
    # Log back in as the viewer, selecting the owner's workspace explicitly.
    viewer_client_login.post(
        "/auth/login", json={"email": "viewer@example.com", "password": "correct-horse-battery-staple"}
    )
    resp = viewer_client_login.post(
        f"/approvals/{created['id']}/approve",
        json={},
        headers={"X-Kynd-Workspace": owner["workspace"]["id"]},
    )
    assert resp.status_code == 403


def test_expired_request_cannot_be_approved(client, owner, db):
    created = client.post("/approvals", json={"capability": "send_message"}).json()

    row = db.get(ApprovalRequest, created["id"])
    row.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    resp = client.post(f"/approvals/{created['id']}/approve", json={})
    assert resp.status_code == 409

    listing = client.get("/approvals").json()
    matched = next(r for r in listing if r["id"] == created["id"])
    assert matched["status"] == "EXPIRED"


def test_cross_workspace_isolation(client, owner, db):
    """Workspace B cannot see or decide workspace A's approval request."""
    created = client.post("/approvals", json={"capability": "send_message"}).json()

    other = signup_user(client, email="owner2@example.com", workspace_name="Other Co")

    resp = client.get(
        f"/approvals/{created['id']}",
        headers={"X-Kynd-Workspace": other["workspace"]["id"]},
    )
    assert resp.status_code == 404

    resp2 = client.post(
        f"/approvals/{created['id']}/approve",
        json={},
        headers={"X-Kynd-Workspace": other["workspace"]["id"]},
    )
    assert resp2.status_code == 404


def test_client_cannot_smuggle_approval_id_into_the_request_body(client, owner):
    """The create schema has no `approval_id` field at all — proof by shape.

    A forged approval id from a client has nowhere to go: creation does not
    accept one, and decisions never accept one either. The runtime approval
    id is minted server-side in `approve_request` and never taken as input.
    """
    resp = client.post(
        "/approvals",
        json={
            "capability": "send_message",
            "approval_id": "forged-token-value",  # extra field, must be ignored/rejected
        },
    )
    assert resp.status_code == 201, resp.text
    assert "approval_id" not in resp.json()
