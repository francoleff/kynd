"""Phase 8 — Audit Center.

Proves the mission's exit gate: real application actions (governance
mutations, approval decisions) generate real audit events answering who,
when, what, which resource, and what outcome — with no fabricated statuses
and no duplication of the runtime's own execution_log/audit_log.
"""

from __future__ import annotations


def test_creating_a_capability_generates_an_audit_event(client, owner):
    resp = client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    )
    assert resp.status_code == 201
    cap_id = resp.json()["id"]

    events = client.get("/audit")
    assert events.status_code == 200
    rows = events.json()
    assert len(rows) == 1
    event = rows[0]
    assert event["event_type"] == "capability.created"
    assert event["outcome"] == "SUCCESS"
    assert event["resource_type"] == "capability"
    assert event["resource_id"] == cap_id
    assert event["actor_user_id"] == owner["user"]["id"]
    assert event["metadata"]["name"] == "send_message"
    assert event["created_at"] is not None


def test_full_governance_lifecycle_produces_ordered_audit_trail(client, owner):
    cap = client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    ).json()
    client.patch(
        f"/governance/capabilities/{cap['id']}", json={"max_calls_per_day": 50}
    )
    rule = client.post(
        "/governance/rules",
        json={
            "name": "block-send",
            "rule_type": "block_capability",
            "config": {"capabilities": ["send_message"]},
        },
    ).json()
    client.patch(f"/governance/rules/{rule['id']}", json={"enabled": False})
    client.delete(f"/governance/rules/{rule['id']}")
    client.delete(f"/governance/capabilities/{cap['id']}")

    events = client.get("/audit").json()
    event_types = [e["event_type"] for e in events]
    # Newest first.
    assert event_types == [
        "capability.deleted",
        "governance_rule.deleted",
        "governance_rule.updated",
        "governance_rule.created",
        "capability.updated",
        "capability.created",
    ]


def test_approval_decision_lifecycle_generates_events(client, owner):
    request = client.post("/approvals", json={"capability": "send_message"}).json()
    client.post(f"/approvals/{request['id']}/approve", json={"note": "ok"})

    events = client.get("/audit", params={"resource_type": "approval_request"}).json()
    event_types = [e["event_type"] for e in events]
    assert event_types == ["approval.approved", "approval.requested"]
    for e in events:
        assert e["approval_request_id"] == request["id"]
        assert e["resource_id"] == request["id"]


def test_reject_generates_rejected_event_not_approved(client, owner):
    request = client.post("/approvals", json={"capability": "send_message"}).json()
    client.post(f"/approvals/{request['id']}/reject", json={"note": "no"})

    events = client.get("/audit", params={"resource_type": "approval_request"}).json()
    event_types = [e["event_type"] for e in events]
    assert "approval.rejected" in event_types
    assert "approval.approved" not in event_types


def test_filter_by_event_type(client, owner):
    client.post("/governance/capabilities", json={"name": "cap_a", "enabled": True})
    client.post("/governance/capabilities", json={"name": "cap_b", "enabled": True})
    client.post(
        "/governance/rules",
        json={"name": "r1", "rule_type": "block_capability", "config": {"capabilities": ["cap_a"]}},
    )

    resp = client.get("/audit", params={"event_type": "capability.created"})
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert all(r["event_type"] == "capability.created" for r in rows)


def test_filter_by_resource(client, owner):
    cap = client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    ).json()
    client.patch(f"/governance/capabilities/{cap['id']}", json={"max_calls_per_day": 5})

    resp = client.get(
        "/audit", params={"resource_type": "capability", "resource_id": cap["id"]}
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 2
    assert all(r["resource_id"] == cap["id"] for r in rows)


def test_unknown_event_type_filter_is_rejected(client, owner):
    resp = client.get("/audit", params={"event_type": "not_a_real_event"})
    assert resp.status_code == 422


def test_get_single_event_by_id(client, owner):
    client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    ).json()
    events = client.get("/audit").json()
    event_id = events[0]["id"]

    resp = client.get(f"/audit/{event_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == event_id


def test_get_unknown_event_id_is_404(client, owner):
    resp = client.get("/audit/aud_nonexistent")
    assert resp.status_code == 404


def test_cross_workspace_isolation(client, owner):
    """Workspace B cannot see or fetch workspace A's audit events."""
    client.post("/governance/capabilities", json={"name": "send_message", "enabled": True})
    events = client.get("/audit").json()
    event_id = events[0]["id"]

    other = client.post(
        "/auth/signup",
        json={
            "email": "audit-other@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Other Audit Co",
            "name": "Other Owner",
        },
    )
    assert other.status_code == 201

    resp = client.get("/audit")
    assert resp.status_code == 200
    assert resp.json() == []

    resp2 = client.get(f"/audit/{event_id}")
    assert resp2.status_code == 404


def test_viewer_can_read_audit_but_not_expected_to_write(client, owner, db):
    """AUDIT_READ is granted to VIEWER in the existing permission matrix —
    prove the endpoint honors it rather than silently requiring more."""
    from sqlalchemy import select

    from kynd_api.models import Membership, Role, User

    client.post("/governance/capabilities", json={"name": "send_message", "enabled": True})

    signup = client.post(
        "/auth/signup",
        json={
            "email": "audit-viewer@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Viewer WS For Audit",
            "name": "Viewer",
        },
    )
    assert signup.status_code == 201

    viewer_user = db.execute(
        select(User).where(User.email == "audit-viewer@example.com")
    ).scalar_one()
    membership = Membership(
        user_id=viewer_user.id, workspace_id=owner["workspace"]["id"], role=Role.VIEWER
    )
    db.add(membership)
    db.commit()

    client.post(
        "/auth/login",
        json={"email": "audit-viewer@example.com", "password": "correct-horse-battery-staple"},
    )
    resp = client.get(
        "/audit", headers={"X-Kynd-Workspace": owner["workspace"]["id"]}
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_no_second_execution_log_is_created(client, owner):
    """The Audit Center never invents an execution outcome — it references
    the runtime's own execution when one exists, never re-derives one."""
    client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    ).json()

    events = client.get("/audit").json()
    assert len(events) == 1
    # This event describes a governance CHANGE, not an execution — it must
    # not carry a fabricated runtime_execution_id.
    assert events[0]["runtime_execution_id"] is None
