"""Tests for the governance gate."""

import pytest

from kynd_runtime.control_plane.governance_gate import GovernanceGate, Action
from kynd_runtime.control_plane.constitution import Constitution


@pytest.fixture
def constitution():
    return Constitution({
        "name": "test-agent",
        "mission": "Test mission",
        "hard_rules": [
            {
                "name": "no-delete",
                "type": "block_action_type",
                "action_types": ["delete", "destroy"],
            },
            {
                "name": "block-production-deploy",
                "type": "block_capability",
                "capabilities": ["deploy_production"],
            },
            {
                "name": "require-approval-id",
                "type": "require_param",
                "param": "approval_id",
            },
            {
                "name": "no-charges-over-1000",
                "type": "block_param_value",
                "param": "destination",
                "blocked_values": ["personal_account"],
            },
        ],
        "capabilities": [
            {"name": "send_email", "max_amount": 0, "max_calls_per_day": 100},
            {"name": "charge_card", "max_amount": 500, "max_calls_per_day": 10},
        ],
    })


@pytest.fixture
def gate(constitution):
    return GovernanceGate(constitution)


class TestGovernanceGate:
    def test_allow_valid_action(self, gate):
        action = Action(type="send", capability="send_email", params={"to": "user@example.com", "approval_id": "abc123"})
        result = gate.check(action)
        assert result.allowed is True
        assert "permitted" in result.reason.lower() or "allowed" in result.reason.lower()

    def test_block_action_type(self, gate):
        action = Action(type="delete", capability="send_email", params={})
        result = gate.check(action)
        assert result.allowed is False
        assert any("no-delete" in v for v in result.violations)

    def test_block_capability(self, gate):
        action = Action(type="deploy", capability="deploy_production", params={})
        result = gate.check(action)
        assert result.allowed is False
        assert any("block-production-deploy" in v for v in result.violations)

    def test_require_param_missing(self, gate):
        action = Action(type="send", capability="send_email", params={})
        result = gate.check(action)
        assert result.allowed is False
        assert any("require-approval-id" in v for v in result.violations)

    def test_require_param_present(self, gate):
        action = Action(type="send", capability="send_email", params={"approval_id": "abc123"})
        result = gate.check(action)
        assert result.allowed is True

    def test_block_param_value(self, gate):
        action = Action(
            type="send",
            capability="send_email",
            params={"approval_id": "abc123", "destination": "personal_account"},
        )
        result = gate.check(action)
        assert result.allowed is False
        assert any("no-charges-over-1000" in v for v in result.violations)

    def test_unknown_capability(self, gate):
        action = Action(type="send", capability="unknown_cap", params={})
        result = gate.check(action)
        assert result.allowed is False
        assert any("Unknown capability" in v for v in result.violations)

    def test_money_cap_exceeded(self, gate):
        action = Action(type="charge", capability="charge_card", params={}, amount=600.0)
        result = gate.check(action)
        assert result.allowed is False
        assert any("exceeds" in v.lower() for v in result.violations)

    def test_money_cap_within_limit(self, gate):
        action = Action(type="charge", capability="charge_card", params={"approval_id": "abc123"}, amount=400.0)
        result = gate.check(action)
        assert result.allowed is True

    def test_multiple_violations(self, gate):
        action = Action(type="delete", capability="deploy_production", params={})
        result = gate.check(action)
        assert result.allowed is False
        assert len(result.violations) >= 2

    def test_gate_result_has_action(self, gate):
        action = Action(type="send", capability="send_email", params={"approval_id": "x"})
        result = gate.check(action)
        assert result.action is action
