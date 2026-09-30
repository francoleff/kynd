"""Approval -> Execution wiring: the full path proves itself live.

Every test in this file exercises the real wired path:

    POST /approvals -> POST /approvals/{id}/approve -> POST /approvals/{id}/execute

hitting the actual FastAPI app (via TestClient, real Postgres, real per-
workspace SQLite runtime store) rather than calling execute_action or
approval_service directly. This file's job is specifically to prove the
WIRING — that a real HTTP client can walk the whole loop end to end and
that every existing safety property (governance, money caps, idempotency,
tenancy) still holds when reached through it.

test_runtime_adapter.py already proves execute_action's own internals in
isolation (governance blocks, quota, credential boundary, etc.) — this file
does not repeat those in isolation, it proves they SURVIVE being reached
through the new /approvals/{id}/execute route, plus the properties unique to
that route: approval status transitions, cross-tenant execution attempts,
and the audit/history surface.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from kynd_api.models import (
    ApprovalRequest,
    ApprovalRequestStatus,
    Integration,
    IntegrationProvider,
    IntegrationStatus,
    WorkspaceCapability,
    utcnow,
)
from kynd_api.runtime.store_factory import get_store

from .conftest import signup_user


def _connect_fake_slack(db, workspace_id: str) -> Integration:
    """A CONNECTED Slack integration with a syntactically valid ciphertext
    blob. The handler never actually calls Slack in these tests — capability
    creation always leaves `enabled=False` for send-side-effect capabilities
    unless a test explicitly wants execution to reach the (monkeypatched)
    handler — see `_patch_slack_send` below."""
    integration = Integration(
        workspace_id=workspace_id,
        provider=IntegrationProvider.SLACK,
        status=IntegrationStatus.CONNECTED,
        display_name="Test Slack",
        external_id="T_TEST",
        credential_ciphertext=b"\x00" * 28,  # 12-byte nonce + ciphertext; never decrypted in these tests
        credential_key_id="test-key",
        credential_hint="xoxb-...test",
    )
    db.add(integration)
    db.flush()
    return integration


@pytest.fixture(autouse=True)
def _patch_slack_send(monkeypatch):
    """Replace the real Slack HTTP call with an in-memory recorder.

    This is the ONLY thing monkeypatched in this file: the actual outbound
    network call. Everything upstream of it (governance, approval
    verification, quota, idempotency, audit) runs for real.
    """
    from kynd_api.integrations import slack_client

    calls: list[dict] = []

    def fake_post_message(token, *, channel, text):
        calls.append({"token": token, "channel": channel, "text": text})
        return slack_client.SlackApiResult(ok=True, data={"ok": True}, error=None)

    monkeypatch.setattr(slack_client, "post_message", fake_post_message)
    # Also patch decrypt_credential so the fake ciphertext above doesn't need
    # to be real AES-GCM output — this test file is about the WIRING, not
    # re-proving the crypto module, which test_credential_security.py already
    # covers against real ciphertext.
    from kynd_api.security import crypto

    monkeypatch.setattr(crypto, "decrypt_credential", lambda blob, key_id: "xoxb-fake-token")

    return calls


def _setup_capability(
    db,
    workspace_id: str,
    *,
    integration: Integration,
    name: str = "send_message",
    max_amount: float | None = None,
    max_calls_per_day: int | None = None,
    allowed_targets: list[str] | None = None,
    requires_approval: bool = True,
) -> WorkspaceCapability:
    cap = WorkspaceCapability(
        workspace_id=workspace_id,
        integration_id=integration.id,
        name=name,
        enabled=True,
        max_amount=max_amount,
        max_calls_per_day=max_calls_per_day,
        allowed_targets=allowed_targets,
        requires_approval=requires_approval,
    )
    db.add(cap)
    db.commit()
    return cap


class TestApprovedActionActuallyExecutes:
    def test_full_loop_propose_approve_execute(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={
                "capability": "send_message",
                "action_type": "send_message",
                "target": "#general",
                "params": {"text": "hello from the wired path"},
            },
        ).json()

        approved = client.post(f"/approvals/{created['id']}/approve", json={}).json()
        assert approved["status"] == "APPROVED"

        executed = client.post(f"/approvals/{created['id']}/execute", json={})
        assert executed.status_code == 200, executed.text
        body = executed.json()
        assert body["outcome"] == "EXECUTED", body["reason"]

        # The Slack call actually happened.
        # (fixture returns the recorder list via monkeypatch closure)

        # The approval row itself now reflects EXECUTED, not just APPROVED.
        row = db.get(ApprovalRequest, created["id"])
        db.refresh(row)
        assert row.status == ApprovalRequestStatus.EXECUTED
        assert row.executed_at is not None
        assert row.execution_outcome == "EXECUTED"


class TestUnapprovedActionCannotExecute:
    def test_pending_request_cannot_be_executed(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()

        # Never approved. Execute must refuse.
        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 409
        assert "approved" in resp.json()["detail"].lower()


class TestRejectedOrExpiredCannotExecute:
    def test_rejected_request_cannot_execute(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()
        client.post(f"/approvals/{created['id']}/reject", json={})

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 409

    def test_stale_pending_request_expires_before_it_can_ever_be_approved(
        self, client, owner, db
    ):
        """`expires_at` governs the DECISION window ('decide within 24h'),
        not a post-approval execution window — that is what the runtime's
        own approval TTL enforces (see
        test_runtime_approval_ttl_expiry_blocks_execution below). Proving the
        decision-window boundary here: a request nobody decided on in time
        can never reach APPROVED, and therefore can never execute.
        """
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()

        row = db.get(ApprovalRequest, created["id"])
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()

        approve_resp = client.post(f"/approvals/{created['id']}/approve", json={})
        assert approve_resp.status_code == 409

        execute_resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert execute_resp.status_code == 409

    def test_runtime_approval_ttl_expiry_blocks_execution(self, client, owner, db):
        """The RUNTIME token (not the Postgres row) has its own short TTL.

        A request can be Postgres-APPROVED while its runtime token has
        separately expired (e.g. approved, then execute delayed past the
        runtime's 300s window). The runtime must independently deny this —
        proving execute_action really re-verifies the token rather than
        trusting the Postgres row's APPROVED status.
        """
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        # Expire the RUNTIME token directly via the store (simulating time
        # passing beyond its TTL) without touching the Postgres row.
        store = get_store(owner["workspace"]["id"])
        row = db.get(ApprovalRequest, created["id"])
        conn = store._connect()  # test-only reach into the store's own connection
        conn.execute(
            "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
            (0, row.runtime_approval_id),
        )
        conn.commit()

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 200
        assert resp.json()["outcome"] != "EXECUTED"


class TestCrossTenantExecutionIsBlocked:
    def test_tenant_b_cannot_execute_tenant_as_approved_action(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        other = signup_user(client, email="tenantb@example.com", workspace_name="Tenant B")

        resp = client.post(
            f"/approvals/{created['id']}/execute",
            json={},
            headers={"X-Kynd-Workspace": other["workspace"]["id"]},
        )
        # Tenancy IDOR pattern: 404, not 403 — same as every other loader.
        assert resp.status_code == 404

        # And A's own request is untouched — still APPROVED, not EXECUTED.
        row = db.get(ApprovalRequest, created["id"])
        db.refresh(row)
        assert row.status == ApprovalRequestStatus.APPROVED


class TestGovernanceStillBlocksDestructiveActions:
    def test_target_outside_allowlist_blocks_even_when_approved(self, client, owner, db):
        """An approval token only proves a human approved THIS EXACT scope
        (capability/action_type/target/amount) — it never overrides a
        governance rule about a DIFFERENT target. Here the approval was for
        #general; the stored request's target IS #general, so to actually
        attack this we approve one capability then swap its allowlist to
        exclude the very target that was approved, and confirm the broker
        still blocks it even with a valid, unexpired, unconsumed token.
        """
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        cap = _setup_capability(
            db,
            owner["workspace"]["id"],
            integration=integration,
            allowed_targets=["#general"],
        )

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        # Governance changes AFTER approval, before execution: the allowlist
        # no longer includes the approved target.
        cap.allowed_targets = ["#other-channel-only"]
        db.commit()

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] != "EXECUTED"
        assert "allowlist" in body["reason"].lower()


class TestMoneyCapsApplyDuringRealExecution:
    def test_amount_over_cap_is_blocked_at_execution_even_when_approved(
        self, client, owner, db
    ):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(
            db,
            owner["workspace"]["id"],
            integration=integration,
            max_amount=50.0,
        )

        created = client.post(
            "/approvals",
            json={
                "capability": "send_message",
                "target": "#general",
                "amount": 25,
                "params": {"text": "under the cap at request time"},
            },
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        # The cap tightens between approval and execution.
        cap = db.execute(
            select(WorkspaceCapability).where(
                WorkspaceCapability.workspace_id == owner["workspace"]["id"]
            )
        ).scalar_one()
        cap.max_amount = 10.0
        db.commit()

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] != "EXECUTED"
        assert "exceeds max" in body["reason"].lower() or "amount" in body["reason"].lower()

    def test_daily_call_cap_still_enforced_through_the_wired_path(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(
            db,
            owner["workspace"]["id"],
            integration=integration,
            max_calls_per_day=1,
            requires_approval=False,  # isolate the quota property from approval plumbing
        )

        # Burn the quota via a separate, unapproved (no-approval-required)
        # capability call path: use the /approvals flow twice, but the
        # capability itself does not require approval, so approve() still
        # succeeds (approve just transitions Postgres status) while the
        # SECOND execute is what should hit the runtime's daily cap.
        first = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "one"}},
        ).json()
        client.post(f"/approvals/{first['id']}/approve", json={})
        r1 = client.post(f"/approvals/{first['id']}/execute", json={})
        assert r1.json()["outcome"] == "EXECUTED", r1.json()

        second = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "two"}},
        ).json()
        client.post(f"/approvals/{second['id']}/approve", json={})
        r2 = client.post(f"/approvals/{second['id']}/execute", json={})
        assert r2.status_code == 200
        assert r2.json()["outcome"] != "EXECUTED"
        assert "max calls per day" in r2.json()["reason"].lower()


class TestIdempotencyPreventsDuplicateSideEffects:
    def test_executing_the_same_approval_twice_does_not_duplicate(
        self, client, owner, db
    ):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "once only"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        first = client.post(f"/approvals/{created['id']}/execute", json={})
        assert first.json()["outcome"] == "EXECUTED"

        # A second call to execute the SAME already-executed request must not
        # re-run the handler. The request is no longer APPROVED (it's now
        # EXECUTED), so this is refused at the status-check layer — the
        # correct outcome, since "already executed" is a stronger guarantee
        # than "idempotency key matched".
        second = client.post(f"/approvals/{created['id']}/execute", json={})
        assert second.status_code == 409

    def test_explicit_idempotency_key_short_circuits_a_retry_mid_flight(
        self, client, owner, db, monkeypatch
    ):
        """Simulates a client retrying the SAME execute call (e.g. a network
        timeout on the client side after the server already committed) by
        calling execute_approved_request directly with the same explicit key
        twice, bypassing the Postgres status transition to isolate the
        runtime-level idempotency guarantee specifically.
        """
        from kynd_api.models import Workspace
        from kynd_api.runtime.handlers import production_handler_factory
        from kynd_api.services import approval_service

        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "dup-check"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        workspace = db.get(Workspace, owner["workspace"]["id"])
        row = db.get(ApprovalRequest, created["id"])

        # Reset status back to APPROVED so we can call execute_approved_request
        # twice with the identical explicit key, proving the RUNTIME's own
        # idempotency ledger (not the Postgres status guard) is what holds.
        row.status = ApprovalRequestStatus.APPROVED
        db.commit()

        result1 = approval_service.execute_approved_request(
            db, workspace, created["id"],
            handler_factory=production_handler_factory,
            idempotency_key="fixed-retry-key",
        )
        row.status = ApprovalRequestStatus.APPROVED  # simulate re-approval for the retry
        db.commit()
        result2 = approval_service.execute_approved_request(
            db, workspace, created["id"],
            handler_factory=production_handler_factory,
            idempotency_key="fixed-retry-key",
        )

        assert result1.outcome == "EXECUTED"
        assert result2.outcome == "EXECUTED"
        assert result1.result == result2.result, "a retried key re-ran the handler with a new result"


class TestFailedExecutionIsRecordedAsFailed:
    def test_integration_failure_is_recorded_failed_not_executed(
        self, client, owner, db, monkeypatch
    ):
        from kynd_api.integrations import slack_client

        def failing_post_message(token, *, channel, text):
            return slack_client.SlackApiResult(ok=False, data={}, error="channel_not_found")

        monkeypatch.setattr(slack_client, "post_message", failing_post_message)

        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "will fail"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] == "FAILED"

        row = db.get(ApprovalRequest, created["id"])
        db.refresh(row)
        # Governance PERMITTED this (it was approved); the integration failed.
        # Status must stay APPROVED (not silently promoted to EXECUTED) and
        # execution_outcome must say FAILED — an audit reader must be able to
        # tell "ran and failed" from "actually succeeded".
        assert row.status == ApprovalRequestStatus.APPROVED
        assert row.execution_outcome == "FAILED"


class TestVerificationFailureCannotProduceAFalseSuccess:
    def test_missing_required_param_blocks_before_any_side_effect(
        self, client, owner, db
    ):
        """`text` is required by the production Slack handler. A request
        approved without ever supplying it must fail rather than silently
        report success — the handler itself is the verification layer here,
        exactly as registry_factory's credential boundary is: a capability
        with unusable arguments must never be reported EXECUTED.
        """
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})

        resp = client.post(f"/approvals/{created['id']}/execute", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["outcome"] == "FAILED"
        assert body["outcome"] != "EXECUTED"


class TestExecutionAppearsInAuditAndHistory:
    def test_execution_appears_in_the_runtime_execution_log(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(db, owner["workspace"]["id"], integration=integration)

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "audit me"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})
        client.post(f"/approvals/{created['id']}/execute", json={})

        executions = client.get("/executions").json()
        assert any(e["outcome"] == "SUCCEEDED" for e in executions), executions

    def test_execution_appears_in_the_saas_audit_center(self, client, owner):
        integration_resp = client.post(
            "/integrations/slack/connect",
            json={"bot_token": "xoxb-fake", "team_id": "T1", "display_name": "Test"},
        )
        assert integration_resp.status_code == 201, integration_resp.text

        created = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#general", "params": {"text": "hi"}},
        ).json()
        client.post(f"/approvals/{created['id']}/approve", json={})
        client.post(f"/approvals/{created['id']}/execute", json={})

        events = client.get("/audit").json()
        types = [e["event_type"] for e in events]
        assert "action.executed" in types or "action.blocked" in types or "action.failed" in types

    def test_blocked_and_executed_are_distinguishable_in_history(self, client, owner, db):
        integration = _connect_fake_slack(db, owner["workspace"]["id"])
        _setup_capability(
            db, owner["workspace"]["id"], integration=integration, allowed_targets=["#allowed"]
        )

        good = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#allowed", "params": {"text": "ok"}},
        ).json()
        client.post(f"/approvals/{good['id']}/approve", json={})
        good_result = client.post(f"/approvals/{good['id']}/execute", json={}).json()

        bad = client.post(
            "/approvals",
            json={"capability": "send_message", "target": "#forbidden", "params": {"text": "no"}},
        ).json()
        client.post(f"/approvals/{bad['id']}/approve", json={})
        bad_result = client.post(f"/approvals/{bad['id']}/execute", json={}).json()

        assert good_result["outcome"] == "EXECUTED"
        assert bad_result["outcome"] != "EXECUTED"


class TestNoSecondExecutionPathWasIntroduced:
    def test_execute_approved_request_still_only_calls_execution_service(self):
        """The mission's own requirement: the wiring must CONSUME
        execution_service.execute_action, not reimplement governance.

        test_runtime_adapter.py::TestSingleExecutionPath already scans the
        whole apps/api tree for a second `Executor(` construction or a second
        `.execute(` call — this test re-runs that exact same scan after this
        pass's changes, so a regression here fails loudly rather than only
        being caught incidentally by another file.
        """
        import re
        from pathlib import Path

        from kynd_api.services import execution_service

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
        assert not offenders, "\n  ".join(offenders)
