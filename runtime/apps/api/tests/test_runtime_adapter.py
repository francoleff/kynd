"""Phase 3: the runtime adapter.

These tests prove the SaaS actually calls the enforcement core and that the
core actually decides. The critical assertion throughout is about SIDE
EFFECTS: a blocked action must not merely return a denial, it must never have
reached the integration handler at all. Every test therefore uses a recording
handler and asserts on what it received — a test that only checks the response
body would pass even if the email had already been sent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from kynd_api.models import (
    GovernanceRule,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
    Membership,
    Workspace,
    WorkspaceCapability,
)
from kynd_api.runtime.constitution_compiler import (
    GovernanceConfigError,
    compile_constitution,
)
from kynd_api.runtime.registry_factory import (
    CredentialInParamsError,
    assert_no_credentials,
)
from kynd_api.runtime.store_factory import InvalidWorkspaceId, store_path
from kynd_api.services import execution_service
from kynd_api.services.execution_service import ExecutionOutcome, execute_action


@pytest.fixture
def recorder():
    """A handler that records every call it receives, and never has side effects.

    This is the instrument the whole file depends on: if `recorder.calls` is
    empty after a blocked action, no side effect happened.
    """

    class Recorder:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def factory(self, integration, capability_name):
            def handler(params):
                self.calls.append(
                    {
                        "capability": capability_name,
                        "integration_id": integration.id,
                        "params": dict(params),
                    }
                )
                return {"ok": True, "capability": capability_name}

            return handler

    return Recorder()


@pytest.fixture
def governed_workspace(client, db, tmp_path, monkeypatch):
    """A workspace with a connected integration and one governed capability."""
    from kynd_api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "runtime_state_dir", str(tmp_path), raising=False)

    signup = client.post(
        "/auth/signup",
        json={
            "email": "gov@runtime-adapter.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Governed Co",
        },
    )
    assert signup.status_code == 201, signup.text
    workspace_id = signup.json()["workspace"]["id"]

    integration = Integration(
        workspace_id=workspace_id,
        provider=IntegrationProvider.SLACK,
        status=IntegrationStatus.CONNECTED,
        display_name="Test Slack",
        credential_ciphertext=b"encrypted-not-a-real-token",
        credential_hint="xoxb-...beef",
    )
    db.add(integration)
    db.flush()

    db.add(
        WorkspaceCapability(
            workspace_id=workspace_id,
            integration_id=integration.id,
            name="send_message",
            enabled=True,
            max_calls_per_day=3,
            allowed_targets=["#general", "#alerts"],
        )
    )
    db.commit()

    workspace = db.get(Workspace, workspace_id)
    return {"workspace": workspace, "integration": integration, "db": db}


class TestConstitutionCompiler:
    def test_compiles_capabilities_into_a_real_constitution(self, db):
        workspace = Workspace(name="Compile Co", slug="compile-co")
        db.add(workspace)
        db.flush()

        capability = WorkspaceCapability(
            workspace_id=workspace.id,
            name="send_email",
            enabled=True,
            max_amount=100.0,
            max_calls_per_day=50,
            allowed_targets=["team@example.com"],
        )

        compiled = compile_constitution(workspace, [capability], [])

        entry = compiled.constitution.get_capability("send_email")
        assert entry is not None
        assert entry["max_amount"] == 100.0
        assert entry["max_calls_per_day"] == 50
        assert entry["allowed_targets"] == ["team@example.com"]

    def test_requires_approval_becomes_a_scoped_hard_rule(self, db):
        workspace = Workspace(name="Approval Co", slug="approval-co")
        db.add(workspace)
        db.flush()

        capability = WorkspaceCapability(
            workspace_id=workspace.id,
            name="send_email",
            enabled=True,
            requires_approval=True,
        )
        compiled = compile_constitution(workspace, [capability], [])

        rules = [
            rule
            for rule in compiled.constitution.hard_rules
            if rule["type"] == "require_param"
        ]
        assert len(rules) == 1
        assert rules[0]["param"] == "approval_id"
        assert rules[0]["verify"] == "approval"
        # Scoped to this capability only: enabling approval for one capability
        # must not start demanding it for every other one.
        assert rules[0]["action_types"] == ["send_email"]

    def test_disabled_capabilities_are_excluded(self, db):
        workspace = Workspace(name="Disabled Co", slug="disabled-co")
        db.add(workspace)
        db.flush()

        compiled = compile_constitution(
            workspace,
            [
                WorkspaceCapability(
                    workspace_id=workspace.id, name="live_one", enabled=True
                ),
                WorkspaceCapability(
                    workspace_id=workspace.id, name="switched_off", enabled=False
                ),
            ],
            [],
        )
        assert compiled.capability_names == ["live_one"]
        assert compiled.constitution.get_capability("switched_off") is None

    def test_unenforceable_rule_type_is_rejected(self, db):
        """A rule the runtime cannot enforce must never be stored.

        Otherwise the UI shows a safety rule that silently does nothing —
        exactly the class of lie the runtime's hardening pass removed.
        """
        workspace = Workspace(name="Bad Rule Co", slug="bad-rule-co")
        db.add(workspace)
        db.flush()

        rule = GovernanceRule(
            workspace_id=workspace.id,
            name="wishful thinking",
            rule_type="be_careful",
            config={},
            enabled=True,
        )

        with pytest.raises(GovernanceConfigError) as exc:
            compile_constitution(workspace, [], [rule])
        assert "cannot enforce" in str(exc.value)

    def test_rule_that_can_never_match_is_rejected(self, db):
        """An empty block list is an inert safety rule. Reject it at save time."""
        workspace = Workspace(name="Inert Co", slug="inert-co")
        db.add(workspace)
        db.flush()

        rule = GovernanceRule(
            workspace_id=workspace.id,
            name="block nothing",
            rule_type="block_action_type",
            config={"action_types": []},
            enabled=True,
        )
        with pytest.raises(GovernanceConfigError) as exc:
            compile_constitution(workspace, [], [rule])
        assert "never block anything" in str(exc.value)

    def test_empty_allowlist_is_preserved_not_collapsed(self, db):
        """[] means 'permit nothing' and None means 'no allowlist'.

        Collapsing the two would silently turn the strictest possible setting
        into the least strict one.
        """
        workspace = Workspace(name="Allowlist Co", slug="allowlist-co")
        db.add(workspace)
        db.flush()

        compiled = compile_constitution(
            workspace,
            [
                WorkspaceCapability(
                    workspace_id=workspace.id,
                    name="locked_down",
                    enabled=True,
                    allowed_targets=[],
                ),
                WorkspaceCapability(
                    workspace_id=workspace.id,
                    name="unrestricted",
                    enabled=True,
                    allowed_targets=None,
                ),
            ],
            [],
        )
        assert compiled.constitution.get_capability("locked_down")["allowed_targets"] == []
        assert "allowed_targets" not in compiled.constitution.get_capability("unrestricted")

    def test_negative_limits_are_rejected(self, db):
        workspace = Workspace(name="Negative Co", slug="negative-co")
        db.add(workspace)
        db.flush()

        with pytest.raises(GovernanceConfigError):
            compile_constitution(
                workspace,
                [
                    WorkspaceCapability(
                        workspace_id=workspace.id,
                        name="bad",
                        enabled=True,
                        max_amount=-5.0,
                    )
                ],
                [],
            )


class TestStorePathIsolation:
    def test_each_workspace_gets_its_own_file(self):
        a = store_path("ws_" + "a" * 32)
        b = store_path("ws_" + "b" * 32)
        assert a != b

    @pytest.mark.parametrize(
        "malicious",
        [
            "ws_../../../etc/passwd",
            "../../secrets",
            "ws_" + "a" * 31,
            "usr_" + "a" * 32,
            "",
            "ws_/../../root",
        ],
    )
    def test_malformed_workspace_ids_are_refused(self, malicious):
        """A workspace id must never be able to escape the state directory."""
        with pytest.raises(InvalidWorkspaceId):
            store_path(malicious)


class TestCredentialsNeverInParams:
    """Audit finding S-1: params are persisted verbatim by the runtime."""

    @pytest.mark.parametrize(
        "key",
        [
            "token",
            "api_key",
            "slack_bot_token",
            "password",
            "Authorization",
            "ACCESS_TOKEN",
            "client-secret",
        ],
    )
    def test_credential_shaped_params_are_refused(self, key):
        with pytest.raises(CredentialInParamsError):
            assert_no_credentials({"target": "#general", key: "sensitive-value"})

    def test_ordinary_params_pass(self):
        assert_no_credentials(
            {"target": "#general", "text": "hello", "amount": 10, "subject": "hi"}
        )

    def test_execute_action_blocks_before_any_side_effect(
        self, governed_workspace, recorder
    ):
        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "slack_bot_token": "xoxb-leaked"},
            handler_factory=recorder.factory,
        )
        assert result.outcome == ExecutionOutcome.BLOCKED
        assert "credential" in result.reason.lower()
        assert recorder.calls == [], "handler ran despite a credential in params"


class TestGovernedExecution:
    def test_allowed_action_reaches_the_handler(self, governed_workspace, recorder):
        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "hello"},
            handler_factory=recorder.factory,
        )
        assert result.outcome == ExecutionOutcome.EXECUTED, result.reason
        assert len(recorder.calls) == 1
        assert recorder.calls[0]["params"]["text"] == "hello"

    def test_target_outside_the_allowlist_is_blocked_with_no_side_effect(
        self, governed_workspace, recorder
    ):
        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#ceo-private", "text": "leak"},
            handler_factory=recorder.factory,
        )
        assert result.outcome == ExecutionOutcome.BLOCKED
        assert "allowlist" in result.reason.lower()
        assert recorder.calls == [], "a blocked action still reached the integration"

    def test_unknown_capability_is_blocked(self, governed_workspace, recorder):
        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="delete_everything",
            params={"target": "#general"},
            handler_factory=recorder.factory,
        )
        assert result.outcome in (
            ExecutionOutcome.BLOCKED,
            ExecutionOutcome.NOT_AVAILABLE,
        )
        assert recorder.calls == []

    def test_daily_quota_is_enforced_and_durable(self, governed_workspace, recorder):
        """The cap is 3. The 4th attempt must be denied — and stay denied
        after the Executor object is discarded, because the count lives in the
        workspace's SQLite store, not in process memory."""
        for i in range(3):
            result = execute_action(
                db=governed_workspace["db"],
                workspace=governed_workspace["workspace"],
                capability="send_message",
                params={"target": "#general", "text": f"msg {i}"},
                handler_factory=recorder.factory,
            )
            assert result.outcome == ExecutionOutcome.EXECUTED, result.reason

        blocked = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "over the line"},
            handler_factory=recorder.factory,
        )
        assert blocked.outcome == ExecutionOutcome.BLOCKED
        assert "max calls per day" in blocked.reason.lower()
        assert len(recorder.calls) == 3, "quota was exceeded at the integration"

    def test_disconnected_integration_removes_the_capability(
        self, governed_workspace, recorder
    ):
        integration = governed_workspace["integration"]
        integration.status = IntegrationStatus.DISCONNECTED
        governed_workspace["db"].commit()

        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "hi"},
            handler_factory=recorder.factory,
        )
        assert result.outcome == ExecutionOutcome.NOT_AVAILABLE
        assert recorder.calls == []

    def test_integration_failure_is_reported_without_leaking_detail(
        self, governed_workspace
    ):
        def exploding_factory(integration, capability_name):
            def handler(params):
                raise RuntimeError(
                    "smtp://user:hunter2@mail.internal refused the connection"
                )

            return handler

        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "hi"},
            handler_factory=exploding_factory,
        )
        assert result.outcome == ExecutionOutcome.FAILED
        # The connection string must not reach the customer.
        assert "hunter2" not in result.reason
        assert "smtp://" not in result.reason

    def test_approval_required_capability_is_denied_without_an_approval(
        self, governed_workspace, recorder
    ):
        capability = (
            governed_workspace["db"]
            .execute(
                select(WorkspaceCapability).where(
                    WorkspaceCapability.workspace_id
                    == governed_workspace["workspace"].id
                )
            )
            .scalar_one()
        )
        capability.requires_approval = True
        governed_workspace["db"].commit()

        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "needs a human"},
            handler_factory=recorder.factory,
            action_type="send_message",
        )
        assert result.outcome == ExecutionOutcome.APPROVAL_REQUIRED
        assert recorder.calls == []

    def test_forged_approval_id_is_rejected(self, governed_workspace, recorder):
        """A made-up approval token must not pass. Audit finding S-4."""
        capability = (
            governed_workspace["db"]
            .execute(
                select(WorkspaceCapability).where(
                    WorkspaceCapability.workspace_id
                    == governed_workspace["workspace"].id
                )
            )
            .scalar_one()
        )
        capability.requires_approval = True
        governed_workspace["db"].commit()

        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "sneaky"},
            handler_factory=recorder.factory,
            action_type="send_message",
            approval_id="totally-made-up-approval-token",
        )
        assert result.outcome in (
            ExecutionOutcome.BLOCKED,
            ExecutionOutcome.APPROVAL_REQUIRED,
        )
        assert recorder.calls == [], "a forged approval produced a real side effect"

    def test_real_issued_approval_permits_execution(self, governed_workspace, recorder):
        """The legitimate path, so the denials above are not merely 'nothing works'."""
        from kynd_api.runtime.store_factory import get_store

        capability = (
            governed_workspace["db"]
            .execute(
                select(WorkspaceCapability).where(
                    WorkspaceCapability.workspace_id
                    == governed_workspace["workspace"].id
                )
            )
            .scalar_one()
        )
        capability.requires_approval = True
        governed_workspace["db"].commit()

        store = get_store(governed_workspace["workspace"].id)
        approval_id = store.issue_approval(
            capability="send_message",
            action_type="send_message",
            target="#general",
            issued_by="test-human",
        )

        result = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "approved by a human"},
            handler_factory=recorder.factory,
            action_type="send_message",
            approval_id=approval_id,
        )
        assert result.outcome == ExecutionOutcome.EXECUTED, result.reason
        assert len(recorder.calls) == 1

    def test_an_approval_cannot_be_reused(self, governed_workspace, recorder):
        """One-time approvals are one-time. The runtime enforces this."""
        from kynd_api.runtime.store_factory import get_store

        capability = (
            governed_workspace["db"]
            .execute(
                select(WorkspaceCapability).where(
                    WorkspaceCapability.workspace_id
                    == governed_workspace["workspace"].id
                )
            )
            .scalar_one()
        )
        capability.requires_approval = True
        governed_workspace["db"].commit()

        store = get_store(governed_workspace["workspace"].id)
        approval_id = store.issue_approval(
            capability="send_message",
            action_type="send_message",
            target="#general",
        )

        first = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "first"},
            handler_factory=recorder.factory,
            action_type="send_message",
            approval_id=approval_id,
        )
        second = execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "replay"},
            handler_factory=recorder.factory,
            action_type="send_message",
            approval_id=approval_id,
        )

        assert first.outcome == ExecutionOutcome.EXECUTED
        assert second.outcome != ExecutionOutcome.EXECUTED
        assert len(recorder.calls) == 1, "a replayed approval executed twice"

    def test_idempotency_key_prevents_double_execution(
        self, governed_workspace, recorder
    ):
        for _ in range(3):
            execute_action(
                db=governed_workspace["db"],
                workspace=governed_workspace["workspace"],
                capability="send_message",
                params={"target": "#general", "text": "only once"},
                handler_factory=recorder.factory,
                idempotency_key="order-4417",
            )
        assert len(recorder.calls) == 1, "the same idempotency key executed twice"


class TestAuditTrail:
    def test_both_allowed_and_blocked_actions_are_recorded(
        self, governed_workspace, recorder
    ):
        from kynd_api.runtime.store_factory import get_store

        execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#general", "text": "allowed"},
            handler_factory=recorder.factory,
        )
        execute_action(
            db=governed_workspace["db"],
            workspace=governed_workspace["workspace"],
            capability="send_message",
            params={"target": "#forbidden", "text": "blocked"},
            handler_factory=recorder.factory,
        )

        rows = get_store(governed_workspace["workspace"].id).recent_execution()
        statuses = [row["status"] for row in rows]
        assert "allowed" in statuses
        assert "denied" in statuses, "a blocked action left no audit trail"


class TestSingleExecutionPath:
    def test_only_the_execution_service_calls_the_executor(self):
        """Mission rule: one canonical execution path.

        Scans the API source for `.execute(` on an Executor. If a second call
        site ever appears, this fails — which is the point, because a second
        path is a governance bypass waiting to happen.
        """
        api_root = Path(execution_service.__file__).resolve().parents[1]
        offenders: list[str] = []

        for path in api_root.rglob("*.py"):
            if path.name == "execution_service.py":
                continue
            source = path.read_text(encoding="utf-8")
            if re.search(r"\bExecutor\s*\(", source):
                offenders.append(f"{path.relative_to(api_root)}: constructs an Executor")
            if re.search(r"executor\s*\.\s*execute\s*\(", source):
                offenders.append(f"{path.relative_to(api_root)}: calls executor.execute")

        assert not offenders, (
            "the Executor must only be reached through execution_service:\n  "
            + "\n  ".join(offenders)
        )
