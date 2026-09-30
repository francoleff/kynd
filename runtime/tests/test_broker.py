"""Tests for the broker."""

import pytest

from kynd_runtime.control_plane.broker import Broker
from kynd_runtime.control_plane.constitution import Constitution


@pytest.fixture
def constitution():
    return Constitution({
        "name": "test-agent",
        "capabilities": [
            {
                "name": "send_email",
                "max_amount": 0,
                "max_calls_per_day": 100,
                "allowed_targets": ["newsletter@kynd.io", "team@kynd.io"],
            },
            {
                "name": "charge_card",
                "max_amount": 500.00,
                "max_calls_per_day": 10,
            },
        ],
    })


@pytest.fixture
def broker(constitution):
    return Broker(constitution)


class TestBroker:
    def test_allow_valid_request(self, broker):
        result = broker.request("send_email", "send", target="newsletter@kynd.io")
        assert result.allowed is True
        assert "allowed" in result.reason.lower()

    def test_deny_unregistered_capability(self, broker):
        result = broker.request("unknown_cap", "do_something")
        assert result.allowed is False
        assert "unregistered" in result.reason.lower()

    def test_deny_exceeded_max_calls(self, broker):
        for _ in range(10):
            broker.request("charge_card", "charge", amount=10)

        result = broker.request("charge_card", "charge", amount=10)
        assert result.allowed is False
        assert "exceeded" in result.reason.lower() or "max calls" in result.reason.lower()

    def test_deny_exceeded_max_amount(self, broker):
        result = broker.request("charge_card", "charge", amount=600.00)
        assert result.allowed is False
        assert "exceeds" in result.reason.lower() or "max" in result.reason.lower()

    def test_deny_target_not_in_allowlist(self, broker):
        result = broker.request("send_email", "send", target="evil@hacker.com")
        assert result.allowed is False
        assert "allowlist" in result.reason.lower() or "not in" in result.reason.lower()

    def test_allow_target_in_allowlist(self, broker):
        result = broker.request("send_email", "send", target="team@kynd.io")
        assert result.allowed is True

    def test_audit_log_on_allow(self, broker):
        broker.request("send_email", "send", target="newsletter@kynd.io")
        assert len(broker.audit_log) == 1
        entry = broker.audit_log[0]
        assert entry.capability == "send_email"
        assert entry.allowed is True

    def test_audit_log_on_deny(self, broker):
        broker.request("unknown_cap", "do_something")
        assert len(broker.audit_log) == 1
        entry = broker.audit_log[0]
        assert entry.allowed is False

    def test_reset_daily_counts(self, broker):
        for _ in range(10):
            broker.request("charge_card", "charge", amount=10)

        broker.reset_daily_counts()
        # After reset, should be able to make calls again
        result = broker.request("charge_card", "charge", amount=10)
        assert result.allowed is True

    def test_call_count_tracks_per_capability(self, broker):
        for _ in range(5):
            broker.request("send_email", "send", target="newsletter@kynd.io")

        # charge_card should still have full quota
        result = broker.request("charge_card", "charge", amount=100)
        assert result.allowed is True

        # send_email should be at 5/100
        assert broker.calls_today("send_email") == 5
        assert broker.calls_today("charge_card") == 1

    def test_none_target_with_allowlist(self, broker):
        """If target is None but allowlist exists, should deny (target required)."""
        result = broker.request("send_email", "send", target=None)
        # None target means no target specified; allowlist requires a specific target
        assert result.allowed is False

    def test_no_allowlist_means_any_target(self, broker):
        """charge_card has no allowed_targets, so any target should be fine."""
        result = broker.request("charge_card", "charge", amount=100, target="anyone")
        assert result.allowed is True
