"""Tests for the Constitution / Governance Builder API (Phase 5).

Proves the mission's Phase 5 exit gate:
- Create a rule that blocks a capability; verify preview shows it blocked and
  simulate returns allowed=false with the rule's name in the reason.
- A rule with an invalid/empty payload is rejected with 422 and never persisted.
- Tenant isolation: workspace B cannot read or modify workspace A's rules.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from kynd_api.models import GovernanceRule, WorkspaceCapability


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_capability(client: TestClient, name: str = "send_message") -> dict:
    """Create a workspace capability via the API."""
    resp = client.post(
        "/governance/capabilities",
        json={"name": name, "enabled": True},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_rule(
    client: TestClient,
    name: str,
    rule_type: str,
    config: dict,
) -> dict:
    """Create a governance rule via the API."""
    resp = client.post(
        "/governance/rules",
        json={"name": name, "rule_type": rule_type, "config": config},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Phase 5 exit gate: block a capability end-to-end
# ---------------------------------------------------------------------------

class TestPhase5ExitGate:
    """The literal Phase 5 exit gate from the implementation plan."""

    def test_create_block_rule_then_preview_shows_blocked(
        self, client: TestClient, owner: dict
    ):
        """Create a rule blocking a capability; preview shows it blocked."""
        # Arrange: a capability exists
        _make_capability(client, "send_message")

        # Act: create a block_capability rule
        rule = _make_rule(
            client,
            name="block-send",
            rule_type="block_capability",
            config={"capabilities": ["send_message"]},
        )
        assert rule["name"] == "block-send"
        assert rule["rule_type"] == "block_capability"

        # Assert: preview shows send_message as blocked
        resp = client.get("/governance/preview")
        assert resp.status_code == 200
        preview = resp.json()
        assert "send_message" in preview["blocked_capabilities"]
        assert "send_message" not in preview["allowed"]

    def test_simulate_blocked_action_returns_denied_with_rule_name(
        self, client: TestClient, owner: dict
    ):
        """Simulate an action against a blocked capability: denied, rule named."""
        _make_capability(client, "send_message")
        _make_rule(
            client,
            name="block-send",
            rule_type="block_capability",
            config={"capabilities": ["send_message"]},
        )

        resp = client.post(
            "/governance/simulate",
            json={"type": "send", "capability": "send_message"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is False
        assert "block-send" in result["reason"]

    def test_simulate_allowed_action_returns_allowed(
        self, client: TestClient, owner: dict
    ):
        """Simulate an action with no blocking rule: allowed."""
        _make_capability(client, "send_message")

        resp = client.post(
            "/governance/simulate",
            json={"type": "send", "capability": "send_message"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is True


# ---------------------------------------------------------------------------
# Invalid rule payload: rejected with 422, never persisted
# ---------------------------------------------------------------------------

class TestInvalidRuleRejected:
    """A rule the runtime cannot enforce is never stored."""

    def test_empty_config_for_block_capability_is_rejected(
        self, client: TestClient, owner: dict, db
    ):
        """block_capability with empty capabilities list -> 422, no row written."""
        resp = client.post(
            "/governance/rules",
            json={
                "name": "empty-rule",
                "rule_type": "block_capability",
                "config": {"capabilities": []},
            },
        )
        assert resp.status_code == 422

        # Prove no row was persisted
        count = db.execute(
            select(GovernanceRule).where(
                GovernanceRule.name == "empty-rule"
            )
        ).scalar_one_or_none()
        assert count is None

    def test_unknown_rule_type_is_rejected(
        self, client: TestClient, owner: dict, db
    ):
        """A rule type the runtime doesn't know -> 422, no row written."""
        resp = client.post(
            "/governance/rules",
            json={
                "name": "unknown-type-rule",
                "rule_type": "teleport_matter",
                "config": {},
            },
        )
        assert resp.status_code == 422
        assert "teleport_matter" in resp.json()["detail"]

        count = db.execute(
            select(GovernanceRule).where(
                GovernanceRule.name == "unknown-type-rule"
            )
        ).scalar_one_or_none()
        assert count is None

    def test_block_param_value_with_empty_blocked_values_is_rejected(
        self, client: TestClient, owner: dict, db
    ):
        """block_param_value with empty blocked_values -> 422, no row written."""
        resp = client.post(
            "/governance/rules",
            json={
                "name": "empty-blocked",
                "rule_type": "block_param_value",
                "config": {"param": "channel", "blocked_values": []},
            },
        )
        assert resp.status_code == 422

        count = db.execute(
            select(GovernanceRule).where(
                GovernanceRule.name == "empty-blocked"
            )
        ).scalar_one_or_none()
        assert count is None


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Workspace B cannot read or modify workspace A's rules."""

    def test_workspace_b_cannot_read_workspace_a_rules(
        self, client: TestClient, owner: dict
    ):
        """Workspace B gets 404 when trying to modify workspace A's rule, and
        cannot see it in their list."""
        # Owner (workspace A) creates a capability and rule
        _make_capability(client, "send_message")
        rule = _make_rule(
            client,
            name="rule-a",
            rule_type="block_capability",
            config={"capabilities": ["send_message"]},
        )

        # Sign up a second user in a different workspace
        other = client.post(
            "/auth/signup",
            json={
                "email": "other@example.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Other Corp",
                "name": "Other Owner",
            },
        )
        assert other.status_code == 201

        # Workspace B tries to PATCH workspace A's rule -> 404
        resp = client.patch(
            f"/governance/rules/{rule['id']}",
            json={"enabled": False},
        )
        assert resp.status_code == 404

        # Workspace B tries to DELETE workspace A's rule -> 404
        resp = client.delete(f"/governance/rules/{rule['id']}")
        assert resp.status_code == 404

        # Workspace B's rule list does not contain workspace A's rule
        resp = client.get("/governance/rules")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_workspace_b_cannot_modify_workspace_a_capability(
        self, client: TestClient, owner: dict
    ):
        """Workspace B gets 404 trying to modify workspace A's capability."""
        cap = _make_capability(client, "send_message")

        client.post(
            "/auth/signup",
            json={
                "email": "other2@example.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Other Corp 2",
                "name": "Other Owner 2",
            },
        )

        resp = client.patch(
            f"/governance/capabilities/{cap['id']}",
            json={"enabled": False},
        )
        assert resp.status_code == 404

        resp = client.delete(f"/governance/capabilities/{cap['id']}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Capability CRUD basics
# ---------------------------------------------------------------------------

class TestCapabilityCrud:
    def test_list_capabilities_empty(self, client: TestClient, owner: dict):
        resp = client.get("/governance/capabilities")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_capability(self, client: TestClient, owner: dict):
        _make_capability(client, "send_message")
        resp = client.get("/governance/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "send_message"
        assert data[0]["enabled"] is True

    def test_create_duplicate_capability_returns_409(
        self, client: TestClient, owner: dict
    ):
        _make_capability(client, "send_message")
        resp = client.post(
            "/governance/capabilities",
            json={"name": "send_message"},
        )
        assert resp.status_code == 409

    def test_update_capability(self, client: TestClient, owner: dict):
        cap = _make_capability(client, "send_message")
        resp = client.patch(
            f"/governance/capabilities/{cap['id']}",
            json={"max_calls_per_day": 100, "requires_approval": True},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["max_calls_per_day"] == 100
        assert updated["requires_approval"] is True

    def test_delete_capability(self, client: TestClient, owner: dict):
        cap = _make_capability(client, "send_message")
        resp = client.delete(f"/governance/capabilities/{cap['id']}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Capability deleted"

        resp = client.get("/governance/capabilities")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Rule CRUD basics
# ---------------------------------------------------------------------------

class TestRuleCrud:
    def test_list_rules_empty(self, client: TestClient, owner: dict):
        resp = client.get("/governance/rules")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_list_rule(self, client: TestClient, owner: dict):
        _make_rule(
            client,
            name="my-rule",
            rule_type="block_capability",
            config={"capabilities": ["send_email"]},
        )
        resp = client.get("/governance/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-rule"

    def test_update_rule(self, client: TestClient, owner: dict):
        rule = _make_rule(
            client,
            name="my-rule",
            rule_type="block_capability",
            config={"capabilities": ["send_email"]},
        )
        resp = client.patch(
            f"/governance/rules/{rule['id']}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    def test_delete_rule(self, client: TestClient, owner: dict):
        rule = _make_rule(
            client,
            name="my-rule",
            rule_type="block_capability",
            config={"capabilities": ["send_email"]},
        )
        resp = client.delete(f"/governance/rules/{rule['id']}")
        assert resp.status_code == 200
        assert resp.json()["message"] == "Rule deleted"

        resp = client.get("/governance/rules")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Preview + simulate edge cases
# ---------------------------------------------------------------------------

class TestPreviewAndSimulate:
    def test_preview_with_no_capabilities(self, client: TestClient, owner: dict):
        resp = client.get("/governance/preview")
        assert resp.status_code == 200
        preview = resp.json()
        assert preview["allowed"] == []
        assert preview["blocked_capabilities"] == []
        assert preview["approval_required"] == []

    def test_preview_shows_approval_required(
        self, client: TestClient, owner: dict
    ):
        _make_capability(client, "send_message",)
        # Set requires_approval via update
        resp = client.get("/governance/capabilities")
        cap_id = resp.json()[0]["id"]
        client.patch(
            f"/governance/capabilities/{cap_id}",
            json={"requires_approval": True},
        )

        resp = client.get("/governance/preview")
        assert resp.status_code == 200
        preview = resp.json()
        assert "send_message" in preview["approval_required"]

    def test_simulate_unknown_capability_is_denied(
        self, client: TestClient, owner: dict
    ):
        """An action for a capability not in the constitution is denied."""
        resp = client.post(
            "/governance/simulate",
            json={"type": "send", "capability": "nonexistent_cap"},
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is False
        assert "Unknown capability" in result["reason"]

    def test_simulate_block_param_value(
        self, client: TestClient, owner: dict
    ):
        """A blocked param value is caught by the gate."""
        _make_capability(client, "send_message")
        _make_rule(
            client,
            name="block-channel",
            rule_type="block_param_value",
            config={"param": "channel", "blocked_values": ["#forbidden"]},
        )

        # Allowed: channel not blocked
        resp = client.post(
            "/governance/simulate",
            json={
                "type": "send",
                "capability": "send_message",
                "params": {"channel": "#general"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

        # Denied: channel is blocked
        resp = client.post(
            "/governance/simulate",
            json={
                "type": "send",
                "capability": "send_message",
                "params": {"channel": "#forbidden"},
            },
        )
        assert resp.status_code == 200
        result = resp.json()
        assert result["allowed"] is False
        assert "block-channel" in result["reason"]

    def test_simulate_does_not_consume_quota(
        self, client: TestClient, owner: dict
    ):
        """Simulating an action is side-effect free: repeated simulations don't
        change the outcome (no quota is consumed)."""
        _make_capability(client, "send_message")

        for _ in range(5):
            resp = client.post(
                "/governance/simulate",
                json={"type": "send", "capability": "send_message"},
            )
            assert resp.status_code == 200
            assert resp.json()["allowed"] is True