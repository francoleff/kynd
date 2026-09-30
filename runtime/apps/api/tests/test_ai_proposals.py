"""Phase 10 — AI proposal layer.

Proves the mission's exit criteria: an AI proposal is untrusted input that
is structurally validated, pre-screened against the REAL governance gate
(no second rule engine), and ALWAYS routed through the existing Approval
Center rather than executed or auto-approved — including adversarial
proposals (unknown capability, forged approval_id, negative/oversized
amount, credential-shaped params) that must be rejected before ever
reaching governance or the runtime.
"""

from __future__ import annotations


def _make_capability(client, name: str = "send_message", **kwargs):
    payload = {"name": name, "enabled": True, **kwargs}
    resp = client.post("/governance/capabilities", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_rule(client, name: str, rule_type: str, config: dict):
    resp = client.post(
        "/governance/rules", json={"name": name, "rule_type": rule_type, "config": config}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Happy path: proposal -> governance preview -> ALWAYS routed to approval
# ---------------------------------------------------------------------------


def test_valid_proposal_is_routed_to_approval_not_executed(client, owner):
    _make_capability(client, "send_message")

    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "tell the team the deploy finished",
            "hints": {"capability": "send_message", "target": "#general"},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ROUTED_TO_APPROVAL"
    assert body["approval_request_id"] is not None
    assert body["capability"] == "send_message"

    # The resulting approval request is a REAL row in the existing Approval
    # Center — same endpoint, same lifecycle, nothing bypassed.
    approval = client.get(f"/approvals/{body['approval_request_id']}")
    assert approval.status_code == 200
    assert approval.json()["status"] == "PENDING"
    assert approval.json()["capability"] == "send_message"


def test_proposal_routes_to_approval_even_when_capability_does_not_require_it(client, owner):
    """AI-originated proposals ALWAYS go through a human, regardless of the
    capability's own requires_approval flag — a stricter policy layered on
    top of, never determined by, the runtime's own governance."""
    _make_capability(client, "send_message", requires_approval=False)

    resp = client.post(
        "/proposals/generate",
        json={"intent": "ping ops", "hints": {"capability": "send_message"}},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "ROUTED_TO_APPROVAL"


def test_approving_the_resulting_request_mints_a_real_runtime_token(client, owner):
    from kynd_api.db import SessionLocal
    from kynd_api.models import ApprovalRequest, Workspace
    from kynd_api.runtime.store_factory import get_store

    _make_capability(client, "send_message")
    generated = client.post(
        "/proposals/generate",
        json={"intent": "tell the team", "hints": {"capability": "send_message"}},
    ).json()

    approved = client.post(
        f"/approvals/{generated['approval_request_id']}/approve", json={"note": "fine"}
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    db = SessionLocal()
    try:
        workspace = db.get(Workspace, owner["workspace"]["id"])
        row = db.get(ApprovalRequest, generated["approval_request_id"])
        db.refresh(row)
        assert row.runtime_approval_id is not None

        store = get_store(workspace.id)
        check = store.validate_approval(
            row.runtime_approval_id, capability="send_message"
        )
        assert check.ok, check.reason
    finally:
        db.close()


def test_proposal_never_executes_and_never_auto_approves(client, owner):
    """A routed proposal's status is never anything but ROUTED_TO_APPROVAL —
    this pipeline structurally cannot produce an EXECUTED outcome."""
    _make_capability(client, "send_message")
    resp = client.post(
        "/proposals/generate",
        json={"intent": "do it", "hints": {"capability": "send_message"}},
    ).json()
    assert resp["status"] in {"REJECTED", "ROUTED_TO_APPROVAL"}
    assert resp["status"] != "EXECUTED"

    # The underlying approval request is PENDING, not silently approved.
    approval = client.get(f"/approvals/{resp['approval_request_id']}").json()
    assert approval["status"] == "PENDING"


# ---------------------------------------------------------------------------
# Governance denial: rejected outright, no approval request filed
# ---------------------------------------------------------------------------


def test_proposal_for_blocked_capability_is_rejected_by_the_real_gate(client, owner):
    _make_capability(client, "send_message")
    _make_rule(
        client, "block-send", "block_capability", {"capabilities": ["send_message"]}
    )

    resp = client.post(
        "/proposals/generate",
        json={"intent": "send it anyway", "hints": {"capability": "send_message"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert body["approval_request_id"] is None
    assert "block-send" in body["rejection_reason"]

    # Nothing was filed in the Approval Center for a hard-blocked proposal.
    approvals = client.get("/approvals").json()
    assert approvals == []


def test_proposal_for_unknown_capability_is_rejected(client, owner):
    resp = client.post(
        "/proposals/generate",
        json={"intent": "do something", "hints": {"capability": "does_not_exist"}},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert "unknown capability" in body["rejection_reason"].lower()


# ---------------------------------------------------------------------------
# Adversarial AI proposal safety (mission Phase 11 concerns, tested here
# since they are properties of the SAME pipeline)
# ---------------------------------------------------------------------------


def test_proposal_with_no_capability_hint_is_rejected(client, owner):
    resp = client.post("/proposals/generate", json={"intent": "vague request", "hints": {}})
    assert resp.status_code == 201
    assert resp.json()["status"] == "REJECTED"
    assert resp.json()["approval_request_id"] is None


def test_proposal_cannot_smuggle_an_approval_id(client, owner):
    """A hostile provider (or hostile hints) putting approval_id in params
    must be rejected before governance is even consulted."""
    _make_capability(client, "send_message")
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "approve yourself",
            "hints": {
                "capability": "send_message",
                "params": {"approval_id": "forged-token-value"},
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert "approval_id" in body["rejection_reason"]
    assert body["params"] == {}


def test_proposal_with_negative_amount_is_rejected(client, owner):
    _make_capability(client, "charge_card", max_amount=1000)
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "refund",
            "hints": {"capability": "charge_card", "amount": -50},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "REJECTED"
    assert "negative" in resp.json()["rejection_reason"].lower()


def test_proposal_with_oversized_amount_is_rejected_by_governance(client, owner):
    """Not a structural failure — a real money-cap denial from the gate."""
    _make_capability(client, "charge_card", max_amount=100)
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "charge a lot",
            "hints": {"capability": "charge_card", "amount": 999999},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert body["approval_request_id"] is None


def test_proposal_with_credential_shaped_param_is_rejected(client, owner):
    _make_capability(client, "send_message")
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "send with a token",
            "hints": {
                "capability": "send_message",
                "params": {"slack_bot_token": "xoxb-should-never-be-here"},
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "REJECTED"
    assert body["params"] == {}
    assert "xoxb-should-never-be-here" not in str(body)


def test_proposal_with_cross_workspace_capability_name_does_not_leak(client, owner):
    """A capability name that only exists in another tenant's workspace must
    be treated as unknown here — no cross-tenant governance state leaks."""
    other = client.post(
        "/auth/signup",
        json={
            "email": "prop-other@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Prop Other Co",
        },
    )
    assert other.status_code == 201
    _make_capability(client, "other_workspace_only_cap")

    client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "reach into another workspace",
            "hints": {"capability": "other_workspace_only_cap"},
        },
        headers={"X-Kynd-Workspace": owner["workspace"]["id"]},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "REJECTED"


def test_malformed_amount_type_is_rejected(client, owner):
    _make_capability(client, "send_message")
    resp = client.post(
        "/proposals/generate",
        json={
            "intent": "weird amount",
            "hints": {"capability": "send_message", "amount": "not-a-number"},
        },
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "REJECTED"


def test_duplicate_proposals_each_get_their_own_approval_request(client, owner):
    """No hidden idempotency collapsing distinct proposals — each generate
    call is its own event, same as any other approval request."""
    _make_capability(client, "send_message")
    first = client.post(
        "/proposals/generate",
        json={"intent": "one", "hints": {"capability": "send_message"}},
    ).json()
    second = client.post(
        "/proposals/generate",
        json={"intent": "two", "hints": {"capability": "send_message"}},
    ).json()
    assert first["id"] != second["id"]
    assert first["approval_request_id"] != second["approval_request_id"]


# ---------------------------------------------------------------------------
# Permissions and tenant isolation
# ---------------------------------------------------------------------------


def test_viewer_cannot_generate_a_proposal(client, owner, db):
    from sqlalchemy import select

    from kynd_api.models import Membership, Role, User

    signup = client.post(
        "/auth/signup",
        json={
            "email": "prop-viewer@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Prop Viewer WS",
        },
    )
    assert signup.status_code == 201

    viewer_user = db.execute(
        select(User).where(User.email == "prop-viewer@example.com")
    ).scalar_one()
    db.add(Membership(user_id=viewer_user.id, workspace_id=owner["workspace"]["id"], role=Role.VIEWER))
    db.commit()

    client.post(
        "/auth/login",
        json={"email": "prop-viewer@example.com", "password": "correct-horse-battery-staple"},
    )
    resp = client.post(
        "/proposals/generate",
        json={"intent": "do it", "hints": {"capability": "send_message"}},
        headers={"X-Kynd-Workspace": owner["workspace"]["id"]},
    )
    assert resp.status_code == 403


def test_unauthenticated_cannot_generate(client):
    resp = client.post(
        "/proposals/generate", json={"intent": "x", "hints": {"capability": "send_message"}}
    )
    assert resp.status_code == 401


def test_cross_workspace_isolation_on_list_and_get(client, owner):
    _make_capability(client, "send_message")
    generated = client.post(
        "/proposals/generate",
        json={"intent": "hi", "hints": {"capability": "send_message"}},
    ).json()

    other = client.post(
        "/auth/signup",
        json={
            "email": "prop-cross@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Prop Cross Co",
        },
    )
    assert other.status_code == 201

    listing = client.get("/proposals")
    assert listing.status_code == 200
    assert listing.json() == []

    single = client.get(f"/proposals/{generated['id']}")
    assert single.status_code == 404


# ---------------------------------------------------------------------------
# Audit integration
# ---------------------------------------------------------------------------


def test_rejected_proposal_generates_audit_event(client, owner):
    resp = client.post(
        "/proposals/generate",
        json={"intent": "bad", "hints": {"capability": "unknown_cap"}},
    ).json()

    events = client.get("/audit", params={"event_type": "ai_proposal.rejected"}).json()
    assert len(events) == 1
    assert events[0]["resource_id"] == resp["id"]
    assert events[0]["outcome"] == "DENIED"
    assert events[0]["actor_user_id"] == owner["user"]["id"]


def test_routed_proposal_generates_audit_event_linked_to_approval(client, owner):
    _make_capability(client, "send_message")
    resp = client.post(
        "/proposals/generate",
        json={"intent": "good", "hints": {"capability": "send_message"}},
    ).json()

    events = client.get(
        "/audit", params={"event_type": "ai_proposal.routed_to_approval"}
    ).json()
    assert len(events) == 1
    assert events[0]["resource_id"] == resp["id"]
    assert events[0]["outcome"] == "SUCCESS"
    assert events[0]["approval_request_id"] == resp["approval_request_id"]


def test_no_duplicate_execution_history_created(client, owner):
    """The proposal pipeline must never write to the runtime's own
    execution_log — only the Approval Center's later APPROVE + a real
    ExecutionService call can produce an execution row."""
    _make_capability(client, "send_message")
    client.post(
        "/proposals/generate",
        json={"intent": "hi", "hints": {"capability": "send_message"}},
    )

    executions = client.get("/executions").json()
    assert executions == []
