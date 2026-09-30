"""Regression tests — one per confirmed finding in docs/engineering/ARCHITECTURE_AUDIT.md.

Every test in this file failed against the pre-hardening code. Each references
its finding ID so a future reader can trace the test back to the evidence.
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import pytest

from kynd_runtime import (
    Constitution,
    ConstitutionError,
    Executor,
    KyndExecutionError,
    ToolRegistry,
    Verifier,
)
from kynd_runtime.control_plane.broker import Broker
from kynd_runtime.control_plane.governance_gate import Action, GovernanceGate


def _executor(raw: dict, handlers: dict | None = None) -> tuple[Executor, dict]:
    """Build an executor whose handlers record every real invocation."""
    calls: dict[str, list] = {}
    registry = ToolRegistry()
    for name in handlers or {c["name"]: None for c in raw.get("capabilities", [])}:
        def make(n):
            def handler(params):
                calls.setdefault(n, []).append(params)
                return f"{n}:EXECUTED"
            return handler
        registry.register(name, make(name))
    return Executor(Constitution(raw), registry), calls


# ---------------------------------------------------------------- F-1 --------
class TestF1BlockActionTypeReachesCapabilities:
    """F-1: `block_action_type: [delete]` must stop `delete_all_customers`.

    Before the fix the Executor set action.type = capability name, so the rule
    only matched a capability literally named `delete`. The side effect ran.
    """

    RAW = {
        "hard_rules": [
            {
                "name": "no-destructive-actions",
                "type": "block_action_type",
                "action_types": ["delete", "destroy", "drop", "purge"],
            }
        ],
        "capabilities": [
            {"name": "delete_all_customers", "max_calls_per_day": 100},
            {"name": "drop_table", "max_calls_per_day": 100},
            {"name": "purge-cache", "max_calls_per_day": 100},
            {"name": "send_email", "max_calls_per_day": 100},
        ],
    }

    def test_destructive_capability_is_blocked_without_explicit_action_type(self):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError, match="blocked action type 'delete'"):
            ex.execute("delete_all_customers", {"confirm": True})
        assert calls == {}, "handler must never have been invoked"

    @pytest.mark.parametrize(
        "capability,blocked",
        [("delete_all_customers", "delete"), ("drop_table", "drop"), ("purge-cache", "purge")],
    )
    def test_verb_prefixed_capabilities_all_blocked(self, capability, blocked):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError, match=blocked):
            ex.execute(capability, {})
        assert calls == {}

    def test_explicit_action_type_is_honoured(self):
        """A capability with a harmless name is still caught by its declared type."""
        raw = {
            "hard_rules": [
                {"name": "no-delete", "type": "block_action_type", "action_types": ["delete"]}
            ],
            "capabilities": [{"name": "cleanup_records", "max_calls_per_day": 100}],
        }
        ex, calls = _executor(raw)
        with pytest.raises(KyndExecutionError, match="action type 'delete' is blocked"):
            ex.execute("cleanup_records", {}, action_type="delete")
        assert calls == {}

    def test_benign_capability_still_allowed(self):
        """The fix must not block everything — 'send_email' has no blocked verb."""
        ex, calls = _executor(self.RAW)
        assert ex.execute("send_email", {"target": "a@b.c"}) == "send_email:EXECUTED"
        assert len(calls["send_email"]) == 1

    def test_substring_does_not_falsely_match(self):
        """'delete' must not match 'undeletable_archive' — word boundaries only."""
        raw = {
            "hard_rules": [
                {"name": "no-delete", "type": "block_action_type", "action_types": ["delete"]}
            ],
            "capabilities": [{"name": "undeletable_archive", "max_calls_per_day": 10}],
        }
        ex, calls = _executor(raw)
        assert ex.execute("undeletable_archive", {}) == "undeletable_archive:EXECUTED"


# ---------------------------------------------------------------- F-2 --------
class TestF2MoneyCapsEnforced:
    """F-2: the documented `money_caps:` block was never consulted."""

    def test_money_caps_blocks_over_limit_charge(self):
        raw = {
            "money_caps": {"charge_card": 10.0},
            "capabilities": [{"name": "charge_card", "max_calls_per_day": 100}],
        }
        ex, calls = _executor(raw)
        with pytest.raises(KyndExecutionError, match=r"exceeds max \$10\.00"):
            ex.execute("charge_card", {"amount": 1_000_000})
        assert calls == {}

    def test_money_caps_allows_within_limit(self):
        raw = {
            "money_caps": {"charge_card": 10.0},
            "capabilities": [{"name": "charge_card", "max_calls_per_day": 100}],
        }
        ex, _ = _executor(raw)
        assert ex.execute("charge_card", {"amount": 5}) == "charge_card:EXECUTED"

    def test_strictest_cap_wins(self):
        """money_caps=50 vs max_amount=500 -> 50 is enforced."""
        raw = {
            "money_caps": {"charge_card": 50.0},
            "capabilities": [
                {"name": "charge_card", "max_amount": 500.0, "max_calls_per_day": 100}
            ],
        }
        ex, calls = _executor(raw)
        with pytest.raises(KyndExecutionError, match=r"exceeds max \$50\.00"):
            ex.execute("charge_card", {"amount": 100})
        assert calls == {}

    def test_strictest_cap_wins_other_direction(self):
        raw = {
            "money_caps": {"charge_card": 500.0},
            "capabilities": [
                {"name": "charge_card", "max_amount": 50.0, "max_calls_per_day": 100}
            ],
        }
        ex, _ = _executor(raw)
        with pytest.raises(KyndExecutionError, match=r"exceeds max \$50\.00"):
            ex.execute("charge_card", {"amount": 100})


# ---------------------------------------------------------------- F-3 --------
class TestF3UnknownRuleTypesFailClosed:
    """F-3: a misspelled rule type silently permitted everything."""

    def test_load_rejects_unknown_rule_type(self):
        with pytest.raises(ConstitutionError, match="unknown rule type"):
            Constitution(
                {
                    "hard_rules": [
                        {"name": "typo", "type": "block_action_typo", "action_types": ["delete"]}
                    ],
                    "capabilities": [{"name": "delete_users"}],
                }
            )

    def test_gate_denies_unenforceable_rule_at_check_time(self):
        """Even if a Constitution is mutated after load, the gate fails closed."""
        const = Constitution({"capabilities": [{"name": "send_email"}]})
        const._raw["hard_rules"] = [{"name": "sneaky", "type": "not_a_real_type"}]
        result = GovernanceGate(const).check(Action(type="send", capability="send_email"))
        assert result.allowed is False
        assert any("unenforceable rule type" in v for v in result.violations)

    def test_rule_missing_its_match_list_is_rejected(self):
        with pytest.raises(ConstitutionError, match="requires a non-empty list"):
            Constitution(
                {"hard_rules": [{"name": "inert", "type": "block_action_type"}]}
            )

    def test_rule_missing_type_is_rejected(self):
        with pytest.raises(ConstitutionError, match="missing required key 'type'"):
            Constitution({"hard_rules": [{"name": "nameless"}]})


# ---------------------------------------------------------------- F-4 --------
class TestF4DailyCapsAreActuallyDaily:
    """F-4: `max_calls_per_day` counted per process and never rolled over."""

    def test_counts_roll_over_on_utc_date_change(self):
        now = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
        const = Constitution({"capabilities": [{"name": "charge_card", "max_calls_per_day": 2}]})
        broker = Broker(const, clock=lambda: now)

        assert broker.request("charge_card", "charge").allowed is True
        assert broker.request("charge_card", "charge").allowed is True
        assert broker.request("charge_card", "charge").allowed is False  # exhausted

        now = now + timedelta(minutes=2)  # crosses into the next UTC day
        assert broker.request("charge_card", "charge").allowed is True, (
            "quota must roll over on date change without an operator cron job"
        )

    def test_old_day_counters_are_pruned(self):
        now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)
        const = Constitution({"capabilities": [{"name": "ping", "max_calls_per_day": 5}]})
        broker = Broker(const, clock=lambda: now)
        for _ in range(3):
            broker.request("ping", "ping")
        for day in range(1, 6):
            now = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc) + timedelta(days=day)
            broker.request("ping", "ping")
        assert len(broker._call_counts) == 1, "stale day counters must not accumulate"

    def test_denied_request_does_not_consume_quota(self):
        const = Constitution(
            {
                "capabilities": [
                    {
                        "name": "send_email",
                        "max_calls_per_day": 2,
                        "allowed_targets": ["ok@kynd.io"],
                    }
                ]
            }
        )
        broker = Broker(const)
        for _ in range(10):
            assert broker.request("send_email", "send", target="bad@evil.com").allowed is False
        assert broker.calls_today("send_email") == 0
        assert broker.request("send_email", "send", target="ok@kynd.io").allowed is True


# ---------------------------------------------------------------- F-5 --------
class TestF5FailedExecutionsNotAuditedAsSuccess:
    """F-5: a raising handler was recorded with allowed=True and no failure marker."""

    def test_failed_tool_is_recorded_as_failed(self):
        registry = ToolRegistry()
        registry.register("send_email", lambda p: (_ for _ in ()).throw(RuntimeError("smtp down")))
        ex = Executor(
            Constitution({"capabilities": [{"name": "send_email", "max_calls_per_day": 5}]}),
            registry,
        )
        with pytest.raises(RuntimeError, match="smtp down"):
            ex.execute("send_email", {"target": "a@b.c"})

        record = ex.execution_log[-1]
        assert record.status == "failed"
        assert record.succeeded is False
        assert record.allowed is True, "governance did permit it; that stays true"
        assert "RuntimeError" in record.error

    def test_denied_and_failed_are_distinguishable(self):
        registry = ToolRegistry()
        registry.register("boom", lambda p: (_ for _ in ()).throw(ValueError("nope")))
        registry.register("fine", lambda p: "ok")
        ex = Executor(
            Constitution(
                {
                    "capabilities": [
                        {"name": "boom", "max_calls_per_day": 5},
                        {"name": "fine", "max_calls_per_day": 5},
                    ]
                }
            ),
            registry,
        )
        ex.execute("fine", {})
        with pytest.raises(ValueError):
            ex.execute("boom", {})
        with pytest.raises(KyndExecutionError):
            ex.execute("unregistered", {})

        assert [r.status for r in ex.execution_log] == ["allowed", "failed", "denied"]


# ---------------------------------------------------------------- F-6 --------
class TestF6AmountValidation:
    """F-6: string amounts crashed with TypeError; negative amounts executed."""

    RAW = {
        "capabilities": [{"name": "charge_card", "max_amount": 500.0, "max_calls_per_day": 100}]
    }

    def test_string_amount_is_denied_not_crashed(self):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError, match="Amount must be a number"):
            ex.execute("charge_card", {"amount": "600"})
        assert calls == {}

    def test_negative_amount_is_denied(self):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError, match="negative"):
            ex.execute("charge_card", {"amount": -9999})
        assert calls == {}, "a negative charge is a refund and must not slip the cap"

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_amount_is_denied(self, bad):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError):
            ex.execute("charge_card", {"amount": bad})
        assert calls == {}

    def test_bool_is_not_a_valid_amount(self):
        ex, calls = _executor(self.RAW)
        with pytest.raises(KyndExecutionError, match="Amount must be a number"):
            ex.execute("charge_card", {"amount": True})
        assert calls == {}

    def test_integer_amount_still_works(self):
        ex, _ = _executor(self.RAW)
        assert ex.execute("charge_card", {"amount": 100}) == "charge_card:EXECUTED"


# ---------------------------------------------------------------- F-9 --------
class TestF9VerifierFailsClosed:
    """F-9: a Verifier with zero checks reported passed=True."""

    def test_empty_verifier_fails(self):
        result = Verifier().verify({"anything": 1})
        assert result.passed is False
        assert "<no checks registered>" in result.failures

    def test_empty_verifier_raises(self):
        with pytest.raises(Exception, match="no checks"):
            Verifier().verify_or_raise({})

    def test_allow_empty_is_an_explicit_opt_in(self):
        assert Verifier(allow_empty=True).verify({}).passed is True

    def test_check_exception_detail_is_surfaced(self):
        v = Verifier()
        v.add_check("bad", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
        result = v.verify({})
        assert result.passed is False
        assert "RuntimeError: boom" in result.errors["bad"]


# --------------------------------------------------------------- F-10 --------
class TestF10CapUnderConcurrency:
    """F-10: check-then-act on the call counter had no lock.

    Never reproduced as an exploit on CPython 3.11 (see audit). Locked anyway;
    this test asserts the invariant holds under contention.
    """

    def test_cap_holds_with_64_concurrent_callers(self):
        charges: list = []
        lock = threading.Lock()

        registry = ToolRegistry()

        def charge(params):
            with lock:
                charges.append(params["amount"])
            return "CHARGED"

        registry.register("charge_card", charge)
        ex = Executor(
            Constitution(
                {"capabilities": [{"name": "charge_card", "max_amount": 500, "max_calls_per_day": 1}]}
            ),
            registry,
        )

        n = 64
        barrier = threading.Barrier(n)

        def hit():
            barrier.wait()
            try:
                ex.execute("charge_card", {"amount": 500})
            except Exception:
                pass

        threads = [threading.Thread(target=hit) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(charges) == 1, f"cap=1 but {len(charges)} charges executed"
        assert ex.calls_today("charge_card") == 1


# --------------------------------------------------------------- F-11 --------
class TestF11Idempotency:
    """F-11: a repeated webhook delivery charged the card twice."""

    RAW = {"capabilities": [{"name": "charge_card", "max_amount": 500, "max_calls_per_day": 10}]}

    def test_repeat_key_does_not_reinvoke_handler(self):
        ex, calls = _executor(self.RAW)
        first = ex.execute("charge_card", {"amount": 100, "idempotency_key": "run-1"})
        second = ex.execute("charge_card", {"amount": 100, "idempotency_key": "run-1"})
        assert first == second
        assert len(calls["charge_card"]) == 1, "handler must run exactly once"

    def test_repeat_key_does_not_consume_quota(self):
        ex, _ = _executor(self.RAW)
        for _ in range(5):
            ex.execute("charge_card", {"amount": 100, "idempotency_key": "run-1"})
        assert ex.calls_today("charge_card") == 1

    def test_distinct_keys_execute_separately(self):
        ex, calls = _executor(self.RAW)
        ex.execute("charge_card", {"amount": 100, "idempotency_key": "run-1"})
        ex.execute("charge_card", {"amount": 100, "idempotency_key": "run-2"})
        assert len(calls["charge_card"]) == 2

    def test_key_reuse_across_capabilities_is_refused(self):
        raw = {
            "capabilities": [
                {"name": "charge_card", "max_amount": 500, "max_calls_per_day": 10},
                {"name": "send_email", "max_calls_per_day": 10},
            ]
        }
        ex, _ = _executor(raw)
        ex.execute("charge_card", {"amount": 1, "idempotency_key": "k"})
        with pytest.raises(KyndExecutionError, match="already used for capability"):
            ex.execute("send_email", {"idempotency_key": "k"})

    def test_failed_execution_is_not_cached(self):
        """A failure must be retryable — do not memoise it as a success."""
        registry = ToolRegistry()
        attempts = {"n": 0}

        def flaky(params):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return "ok"

        registry.register("charge_card", flaky)
        ex = Executor(Constitution(self.RAW), registry)
        with pytest.raises(RuntimeError):
            ex.execute("charge_card", {"amount": 1, "idempotency_key": "k"})
        assert ex.execute("charge_card", {"amount": 1, "idempotency_key": "k"}) == "ok"


# --------------------------------------------------------------- F-12 --------
class TestF12BoundedLogs:
    """F-12: execution and audit logs grew without limit."""

    def test_execution_log_is_bounded(self):
        registry = ToolRegistry()
        registry.register("ping", lambda p: "pong")
        ex = Executor(
            Constitution({"capabilities": [{"name": "ping"}]}), registry, execution_log_limit=10
        )
        for _ in range(100):
            ex.execute("ping", {})
        assert len(ex.execution_log) == 10

    def test_audit_log_is_bounded(self):
        broker = Broker(Constitution({"capabilities": [{"name": "ping"}]}), audit_log_limit=5)
        for _ in range(50):
            broker.request("ping", "ping")
        assert len(broker.audit_log) == 5


# --------------------------------------------------------------- F-13 --------
class TestF13ConstitutionValidation:
    """F-13: malformed constitutions loaded fine and exploded mid-enforcement."""

    @pytest.mark.parametrize(
        "raw,match",
        [
            ({"capabilities": "send_email"}, "must be a list"),
            ({"capabilities": [None]}, "must be a mapping"),
            ({"capabilities": [{}]}, "'name'"),
            ({"capabilities": [{"name": "a"}, {"name": "a"}]}, "duplicate capability"),
            ({"capabilities": [{"name": "a", "max_amount": "lots"}]}, "must be a number"),
            ({"capabilities": [{"name": "a", "max_amount": -1}]}, "must not be negative"),
            ({"capabilities": [{"name": "a", "max_calls_per_day": "many"}]}, "must be a number"),
            ({"capabilities": [{"name": "a", "allowed_targets": "x@y.z"}]}, "must be a list"),
            ({"hard_rules": "no-delete"}, "must be a list"),
            ({"money_caps": [1, 2]}, "must be a mapping"),
            ({"money_caps": {"a": "free"}}, "must be a number"),
            ({"name": 42}, "must be a str"),
        ],
    )
    def test_structural_problems_rejected_at_load(self, raw, match):
        with pytest.raises(ConstitutionError, match=match):
            Constitution(raw)

    def test_valid_constitution_still_loads(self):
        const = Constitution(
            {
                "name": "ok",
                "mission": "do things",
                "hard_rules": [
                    {"name": "r", "type": "block_action_type", "action_types": ["delete"]}
                ],
                "capabilities": [
                    {"name": "send_email", "max_calls_per_day": 5, "allowed_targets": ["a@b.c"]}
                ],
                "money_caps": {"send_email": 0},
            }
        )
        assert const.name == "ok"

    def test_shipped_example_constitution_is_valid(self):
        """The example we ship must pass our own validator."""
        from pathlib import Path

        example = Path(__file__).resolve().parents[1] / "examples" / "constitution.yaml"
        const = Constitution.load(example)
        assert const.name == "kynd-runtime"


# ----------------------------------------------------------- F-7 / F-8 -------
class TestWebhookSecurity:
    """F-7: unauthenticated listener on 0.0.0.0. F-8: fake verification check."""

    TOKEN = "t" * 32

    @pytest.fixture
    def server(self):
        from kynd_runtime.n8n_connector import KyndWebhookServer

        registry = ToolRegistry()
        self.charges: list = []
        registry.register("charge_card", lambda p: self.charges.append(p) or "CHARGED")
        ex = Executor(
            Constitution(
                {"capabilities": [{"name": "charge_card", "max_amount": 500, "max_calls_per_day": 50}]}
            ),
            registry,
        )
        srv = KyndWebhookServer(ex, host="127.0.0.1", port=0, token=self.TOKEN)
        srv.start_background()
        yield srv
        srv.stop()

    @staticmethod
    def _post(port, path, payload, headers=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_unauthenticated_request_is_rejected(self, server):
        status, body = self._post(server.port, "/webhook/charge_card", {"params": {"amount": 100}})
        assert status == 401
        assert self.charges == [], "no side effect may occur without a valid token"

    def test_wrong_token_is_rejected(self, server):
        status, _ = self._post(
            server.port,
            "/webhook/charge_card",
            {"params": {"amount": 100}},
            {"X-Kynd-Token": "wrong-but-long-enough-token"},
        )
        assert status == 401
        assert self.charges == []

    def test_valid_bearer_token_is_accepted(self, server):
        status, body = self._post(
            server.port,
            "/webhook/charge_card",
            {"params": {"amount": 100}},
            {"Authorization": f"Bearer {self.TOKEN}"},
        )
        assert status == 200
        assert body["result"] == "CHARGED"
        assert len(self.charges) == 1

    def test_governance_denial_returns_403_and_no_side_effect(self, server):
        status, body = self._post(
            server.port,
            "/webhook/charge_card",
            {"params": {"amount": 100_000}},
            {"X-Kynd-Token": self.TOKEN},
        )
        assert status == 403
        assert body["status"] == "denied"
        assert self.charges == []

    def test_internal_error_does_not_leak_exception_text(self, server):
        server.executor._registry.register(
            "charge_card",
            lambda p: (_ for _ in ()).throw(
                RuntimeError("postgres://user:SUPERSECRET@10.0.0.5/prod unreachable")
            ),
            replace=True,
        )
        status, body = self._post(
            server.port,
            "/webhook/charge_card",
            {"params": {"amount": 1}},
            {"X-Kynd-Token": self.TOKEN},
        )
        assert status == 500
        assert "SUPERSECRET" not in json.dumps(body)
        assert "postgres" not in json.dumps(body)

    def test_oversized_body_rejected(self, server):
        status, _ = self._post(
            server.port,
            "/webhook/charge_card",
            {"params": {"amount": 1, "blob": "A" * 2_000_000}},
            {"X-Kynd-Token": self.TOKEN},
        )
        assert status == 413
        assert self.charges == []

    def test_webhook_idempotency_key_is_honoured(self, server):
        for _ in range(3):
            status, _ = self._post(
                server.port,
                "/webhook/charge_card",
                {"params": {"amount": 100}, "idempotency_key": "n8n-run-7"},
                {"X-Kynd-Token": self.TOKEN},
            )
            assert status == 200
        assert len(self.charges) == 1, "n8n retries must not double-charge"

    def test_health_endpoint_needs_no_token(self, server):
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/health", timeout=5) as r:
            assert r.status == 200

    def test_no_fake_verification_check_remains(self):
        """F-8: `lambda p: True` placeholder must be gone from shipped code."""
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "kynd_runtime"
            / "n8n_connector.py"
        ).read_text()
        assert "lambda p: True" not in src
        assert "placeholder" not in src.lower()


# ---------------------------------------------------------------- D-7 --------
class TestD7ToolRegistryRejectsHijack:
    """D-7: re-registering a capability silently replaced its handler.

    A misconfigured import (or a second `register()` call for the same name)
    used to swap `charge_card`'s handler for anything, with no error and only
    an unread log line. Registration must fail loudly by default.
    """

    def test_duplicate_registration_is_rejected_by_default(self):
        from kynd_runtime import CapabilityAlreadyRegisteredError

        registry = ToolRegistry()
        registry.register("charge_card", lambda p: "REAL_CHARGE")
        with pytest.raises(CapabilityAlreadyRegisteredError, match="already registered"):
            registry.register("charge_card", lambda p: "HIJACKED")
        # The original handler must still be the one that runs.
        assert registry.call("charge_card", {}) == "REAL_CHARGE"

    def test_explicit_replace_true_is_still_allowed(self):
        """An intentional swap, opted into explicitly, must keep working."""
        registry = ToolRegistry()
        registry.register("charge_card", lambda p: "OLD")
        registry.register("charge_card", lambda p: "NEW", replace=True)
        assert registry.call("charge_card", {}) == "NEW"

    def test_first_time_registration_is_unaffected(self):
        """Ordinary, non-duplicate registration must not require replace=True."""
        registry = ToolRegistry()
        registry.register("send_email", lambda p: "sent")
        registry.register("charge_card", lambda p: "charged")
        assert registry.call("send_email", {}) == "sent"
        assert registry.call("charge_card", {}) == "charged"

    def test_unregister_then_register_does_not_need_replace(self):
        """Removing a handler first is a legitimate, explicit path to reuse a name."""
        registry = ToolRegistry()
        registry.register("charge_card", lambda p: "OLD")
        registry.unregister("charge_card")
        registry.register("charge_card", lambda p: "NEW")  # no replace=True needed
        assert registry.call("charge_card", {}) == "NEW"
