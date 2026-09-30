"""Integration test: full gate → broker → execute → audit loop."""

import pytest

from kynd_runtime import (
    Constitution,
    Executor,
    KyndExecutionError,
    ToolRegistry,
)


@pytest.fixture
def constitution():
    return Constitution({
        "name": "test-agent",
        "mission": "A test agent for integration",
        "hard_rules": [
            {
                "name": "no-delete",
                "type": "block_action_type",
                "action_types": ["delete", "destroy"],
            },
        ],
        "capabilities": [
            {
                "name": "send_email",
                "max_amount": 0,
                "max_calls_per_day": 3,
                "allowed_targets": ["newsletter@kynd.io", "team@kynd.io"],
            },
            {
                "name": "charge_card",
                "max_amount": 500.00,
                "max_calls_per_day": 2,
            },
        ],
    })


@pytest.fixture
def registry():
    reg = ToolRegistry()

    # Register handlers that record what they were called with
    calls = {}

    def make_handler(name):
        def handler(params):
            calls[name] = params
            return f"{name}_ok"
        return handler

    reg.register("send_email", make_handler("send_email"))
    reg.register("charge_card", make_handler("charge_card"))

    return reg


@pytest.fixture
def executor(constitution, registry):
    return Executor(constitution, registry)


class TestExecutorIntegration:
    def test_full_loop_allow(self, executor):
        """A valid action passes gate → broker → tool → audit."""
        result = executor.execute("send_email", {
            "target": "newsletter@kynd.io",
            "subject": "Hello",
        })
        assert result == "send_email_ok"
        assert len(executor.execution_log) == 1
        assert executor.execution_log[0].allowed is True

    def test_gate_blocks_bad_action(self, executor):
        """Gate blocks an action that violates a hard rule."""
        with pytest.raises(KyndExecutionError, match="Blocked by governance gate"):
            executor.execute("delete", {"target": "something"})
        assert len(executor.execution_log) == 1
        assert executor.execution_log[0].allowed is False

    def test_broker_blocks_over_cap(self, executor):
        """Broker blocks when max calls exceeded."""
        executor.execute("charge_card", {"amount": 100})
        executor.execute("charge_card", {"amount": 100})
        # Third call should be blocked by broker
        with pytest.raises(KyndExecutionError, match="exceeded max calls"):
            executor.execute("charge_card", {"amount": 100})
        # The third execution is recorded as denied
        assert len(executor.execution_log) == 3
        assert executor.execution_log[2].allowed is False

    def test_broker_blocks_over_amount(self, executor):
        """Broker blocks when max amount exceeded."""
        with pytest.raises(KyndExecutionError, match="exceeds max"):
            executor.execute("charge_card", {"amount": 600})
        assert executor.execution_log[0].allowed is False

    def test_broker_blocks_bad_target(self, executor):
        """Broker blocks when target not in allowlist."""
        with pytest.raises(KyndExecutionError, match="not in allowlist"):
            executor.execute("send_email", {"target": "evil@hacker.com"})
        assert executor.execution_log[0].allowed is False

    def test_unknown_capability_raises(self, executor):
        """Gate blocks unknown capabilities."""
        with pytest.raises(KyndExecutionError):
            executor.execute("unknown_cap", {})
        assert executor.execution_log[0].allowed is False

    def test_audit_log_tracks_everything(self, executor):
        """Audit log captures all allow + deny attempts."""
        # 2 allowed charge_card calls
        executor.execute("charge_card", {"amount": 100})
        executor.execute("charge_card", {"amount": 200})
        # 1 denied (over cap)
        with pytest.raises(KyndExecutionError):
            executor.execute("charge_card", {"amount": 50})
        # 1 denied (bad target)
        with pytest.raises(KyndExecutionError):
            executor.execute("send_email", {"target": "bad"})

        # Audit log should have 4 entries
        assert len(executor.audit_log) == 4
        # First two allowed
        assert executor.audit_log[0].allowed is True
        assert executor.audit_log[1].allowed is True
        # Last two denied
        assert executor.audit_log[2].allowed is False
        assert executor.audit_log[3].allowed is False

    def test_execution_log_includes_results(self, executor):
        """Execution log includes tool results for allowed actions."""
        executor.execute("send_email", {"target": "newsletter@kynd.io"})
        record = executor.execution_log[0]
        assert record.allowed is True
        assert record.result == "send_email_ok"

    def test_reset_daily_counts(self, executor):
        """After reset, caps are cleared."""
        executor.execute("charge_card", {"amount": 100})
        executor.execute("charge_card", {"amount": 100})
        # Blocked
        with pytest.raises(KyndExecutionError):
            executor.execute("charge_card", {"amount": 100})
        # Reset
        executor.reset_daily_counts()
        # Now should work
        result = executor.execute("charge_card", {"amount": 100})
        assert result == "charge_card_ok"
