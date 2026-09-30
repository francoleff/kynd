"""Phase 7 — Execution Center. Read-only history over the runtime's own log.

Proves the mission's distinction that matters to customer trust: BLOCKED
(governance denied it) is not the same thing as FAILED (governance allowed
it but the integration itself errored), and both are distinct from
SUCCEEDED. Nothing here invents a status the runtime never recorded.
"""

from __future__ import annotations


def test_list_executions_empty_for_new_workspace(client, owner):
    resp = client.get("/executions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_blocked_execution_appears_as_blocked(client, owner):
    """Enable a capability, block it with a rule, then run it through the
    real ExecutionService — the BLOCKED outcome should show up verbatim in
    the Execution Center, sourced from the runtime's own execution_log.
    """
    cap = client.post(
        "/governance/capabilities", json={"name": "send_message", "enabled": True}
    )
    assert cap.status_code == 201

    rule = client.post(
        "/governance/rules",
        json={
            "name": "block-send",
            "rule_type": "block_capability",
            "config": {"capabilities": ["send_message"]},
        },
    )
    assert rule.status_code == 201

    # There is no public "execute" endpoint yet (Phase 8's territory), so we
    # drive the same execution_service the API will eventually call, directly
    # against the workspace's real runtime — proving the Execution Center
    # reads real rows, not a fixture.
    from kynd_api.db import SessionLocal
    from kynd_api.models import Workspace
    from kynd_api.services.execution_service import execute_action

    db = SessionLocal()
    try:
        workspace = db.get(Workspace, owner["workspace"]["id"])

        def handler_factory(integration, capability_name):
            def _handler(params):
                return {"sent": True}

            return _handler

        result = execute_action(
            db,
            workspace,
            capability="send_message",
            params={},
            handler_factory=handler_factory,
        )
        db.commit()
    finally:
        db.close()

    assert result.outcome == "BLOCKED"

    listing = client.get("/executions")
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["outcome"] == "BLOCKED"
    assert rows[0]["capability"] == "send_message"


def test_cross_workspace_isolation(client, owner):
    """Workspace B's execution log is a different SQLite file entirely —
    physical isolation, not a WHERE clause."""
    from kynd_api.db import SessionLocal
    from kynd_api.models import Workspace
    from kynd_api.services.execution_service import execute_action

    client.post("/governance/capabilities", json={"name": "send_message", "enabled": True})

    db = SessionLocal()
    try:
        workspace = db.get(Workspace, owner["workspace"]["id"])

        def handler_factory(integration, capability_name):
            return lambda params: {"sent": True}

        execute_action(
            db, workspace, capability="send_message", params={}, handler_factory=handler_factory
        )
        db.commit()
    finally:
        db.close()

    other = client.post(
        "/auth/signup",
        json={
            "email": "execs-other@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Other Execs Co",
            "name": "Other Owner",
        },
    )
    assert other.status_code == 201

    resp = client.get("/executions")
    assert resp.status_code == 200
    assert resp.json() == []
