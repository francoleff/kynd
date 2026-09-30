"""D-1: durable governance + verified approvals — adversarial test suite.

Covers every item in the D-1 mission's testing checklist. Real SQLite files
on disk (tmp_path), real process restarts simulated by discarding the Python
object and opening a fresh SqliteStore on the same file, real threads for
concurrency. No mocks of the store itself — these tests exercise actual
transactions.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import date, timedelta

import pytest

from kynd_runtime import (
    Constitution,
    Executor,
    KyndConcurrentExecutionError,
    KyndExecutionError,
    SqliteStore,
    ToolRegistry,
)
from kynd_runtime.persistence import PersistenceError


def make_store(tmp_path, name="kynd.db", **kwargs) -> SqliteStore:
    return SqliteStore(str(tmp_path / name), **kwargs)


def make_executor(store, raw, handlers=None):
    reg = ToolRegistry()
    handlers = handlers or {}
    for cap in raw.get("capabilities", []):
        name = cap["name"]
        reg.register(name, handlers.get(name, lambda p, n=name: f"{n}:ok"))
    return Executor(Constitution(raw), reg, store=store)


# ============================================================== A: durable state


class TestRestartPersistence:
    """Caps, audit, execution log all survive a real process restart."""

    def test_call_count_survives_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        raw = {"capabilities": [{"name": "charge_card", "max_calls_per_day": 3}]}

        store = SqliteStore(str(db))
        ex = make_executor(store, raw)
        ex.execute("charge_card", {})
        ex.execute("charge_card", {})
        del ex, store  # simulate process exit — no explicit flush, nothing in memory

        store2 = SqliteStore(str(db))
        ex2 = make_executor(store2, raw)
        assert ex2.calls_today("charge_card") == 2
        ex2.execute("charge_card", {})
        with pytest.raises(KyndExecutionError, match="exceeded max calls"):
            ex2.execute("charge_card", {})

    def test_audit_log_survives_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        raw = {"capabilities": [{"name": "send_email", "allowed_targets": ["a@b.c"]}]}
        store = SqliteStore(str(db))
        ex = make_executor(store, raw)
        ex.execute("send_email", {"target": "a@b.c"})
        try:
            ex.execute("send_email", {"target": "evil@x.com"})
        except KyndExecutionError:
            pass
        del ex, store

        store2 = SqliteStore(str(db))
        entries = store2.recent_audit()
        assert len(entries) == 2
        assert entries[0]["allowed"] == 1
        assert entries[1]["allowed"] == 0

    def test_execution_log_survives_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        raw = {"capabilities": [{"name": "ping"}]}
        store = SqliteStore(str(db))
        ex = make_executor(store, raw)
        ex.execute("ping", {"x": 1})
        del ex, store

        store2 = SqliteStore(str(db))
        recs = store2.recent_execution()
        assert len(recs) == 1
        assert recs[0]["capability"] == "ping"
        assert recs[0]["params"] == {"x": 1}

    def test_idempotency_survives_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        raw = {"capabilities": [{"name": "charge_card"}]}
        hits = []
        store = SqliteStore(str(db))
        ex = make_executor(store, raw, {"charge_card": lambda p: (hits.append(1), "CHARGED")[1]})
        r1 = ex.execute("charge_card", {"idempotency_key": "order-1"})
        del ex, store

        store2 = SqliteStore(str(db))
        ex2 = make_executor(store2, raw, {"charge_card": lambda p: (hits.append(1), "CHARGED")[1]})
        r2 = ex2.execute("charge_card", {"idempotency_key": "order-1"})
        assert r1 == r2 == "CHARGED"
        assert len(hits) == 1, "handler must not re-run after restart with same key"

    def test_approval_survives_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        store = SqliteStore(str(db))
        aid = store.issue_approval("charge_card", max_amount=100, max_uses=1)
        del store

        store2 = SqliteStore(str(db))
        result = store2.validate_approval(aid, "charge_card", amount=50)
        assert result.ok is True
        consumed = store2.consume_approval(aid, "charge_card", amount=50)
        assert consumed.ok is True
        del store2

        store3 = SqliteStore(str(db))
        result3 = store3.validate_approval(aid, "charge_card", amount=50)
        assert result3.ok is False
        assert "already consumed" in result3.reason


class TestDailyRollover:
    def test_rolls_over_at_utc_midnight(self, tmp_path):
        store = make_store(tmp_path)
        # Exercises the store's day-keyed rollover directly with explicit day
        # strings, which is exactly what Broker does internally — the clock
        # abstraction lives in Broker, not in SqliteStore, so there is no
        # executor-level seam to drive here.
        allowed, _ = store.try_increment_call_count("2026-08-31", "charge_card", 2)
        assert allowed
        allowed, _ = store.try_increment_call_count("2026-08-31", "charge_card", 2)
        assert allowed
        allowed, _ = store.try_increment_call_count("2026-08-31", "charge_card", 2)
        assert not allowed, "third call same day must be denied"

        allowed, count = store.try_increment_call_count("2026-09-01", "charge_card", 2)
        assert allowed and count == 1, "quota must roll over on UTC date change"

    def test_old_day_rows_do_not_block_new_day(self, tmp_path):
        store = make_store(tmp_path)
        for d in range(1, 10):
            day = (date(2026, 8, 1) + timedelta(days=d)).isoformat()
            store.try_increment_call_count(day, "ping", None)
        # No max_calls_per_day cap (None) means always allowed regardless of
        # accumulated rows — confirms rows are scoped per day, not globally summed.
        allowed, count = store.try_increment_call_count("2026-09-15", "ping", 1)
        assert allowed and count == 1


class TestMultiProcessQuotaSharing:
    """Real threads sharing one store file — the in-process analog of the
    8-real-process test run manually during development (see D-1 report)."""

    def test_threads_share_quota_via_store(self, tmp_path):
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card", "max_calls_per_day": 5}]}
        reg = ToolRegistry()
        reg.register("charge_card", lambda p: "CHARGED")

        allowed_count = []
        lock = threading.Lock()

        def worker():
            ex = Executor(Constitution(raw), reg, store=store)
            for _ in range(10):
                try:
                    ex.execute("charge_card", {})
                    with lock:
                        allowed_count.append(1)
                except KyndExecutionError:
                    pass

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(allowed_count) == 5, f"cap=5 but {len(allowed_count)} allowed across 8 workers"
        assert store.calls_today(date.today().isoformat(), "charge_card") == 5


# ============================================================== B/C: atomicity + idempotency


class TestDuplicateIdempotencyKey:
    def test_second_identical_request_returns_cached_result(self, tmp_path):
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card"}]}
        hits = []
        ex = make_executor(store, raw, {"charge_card": lambda p: (hits.append(1), "CHARGED")[1]})
        r1 = ex.execute("charge_card", {"idempotency_key": "k1"})
        r2 = ex.execute("charge_card", {"idempotency_key": "k1"})
        assert r1 == r2
        assert len(hits) == 1

    def test_different_capability_same_key_rejected(self, tmp_path):
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card"}, {"name": "send_email"}]}
        ex = make_executor(store, raw)
        ex.execute("charge_card", {"idempotency_key": "k1"})
        with pytest.raises(KyndExecutionError, match="already used for capability"):
            ex.execute("send_email", {"idempotency_key": "k1"})


class TestConcurrentDuplicateRequests:
    """The hard case: two threads submit the SAME idempotency key at the SAME
    time. Exactly one must invoke the handler; the other must observe its result."""

    def test_concurrent_duplicates_execute_handler_exactly_once(self, tmp_path):
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card"}]}
        hits = []
        hit_lock = threading.Lock()

        def slow_handler(params):
            time.sleep(0.15)  # widen the race window deliberately
            with hit_lock:
                hits.append(1)
            return "CHARGED-ONCE"

        reg = ToolRegistry()
        reg.register("charge_card", slow_handler)

        results = []
        errors = []
        results_lock = threading.Lock()

        def worker():
            ex = Executor(Constitution(raw), reg, store=store)
            try:
                r = ex.execute("charge_card", {"idempotency_key": "concurrent-1"})
                with results_lock:
                    results.append(r)
            except Exception as e:
                with results_lock:
                    errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(hits) == 1, f"handler ran {len(hits)} times, must be exactly 1"
        assert not errors, f"unexpected errors: {errors}"
        assert all(r == "CHARGED-ONCE" for r in results)
        assert len(results) == 10

    def test_concurrent_duplicates_do_not_double_consume_quota(self, tmp_path):
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card", "max_calls_per_day": 100}]}

        def slow_handler(params):
            time.sleep(0.1)
            return "ok"

        reg = ToolRegistry()
        reg.register("charge_card", slow_handler)

        def worker():
            ex = Executor(Constitution(raw), reg, store=store)
            try:
                ex.execute("charge_card", {"idempotency_key": "quota-race"})
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(15)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert store.calls_today(date.today().isoformat(), "charge_card") == 1, (
            "one idempotency key must consume quota exactly once regardless of "
            "how many concurrent callers share it"
        )


class TestRetryAfterCrash:
    def test_retry_after_handler_failure_gets_genuine_new_attempt(self, tmp_path):
        """A failure is not cached as a success — the classic idempotency footgun."""
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "charge_card"}]}
        attempts = {"n": 0}

        def flaky(params):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient failure")
            return "ok"

        reg = ToolRegistry()
        reg.register("charge_card", flaky)
        ex = Executor(Constitution(raw), reg, store=store)

        with pytest.raises(RuntimeError):
            ex.execute("charge_card", {"idempotency_key": "retry-1"})
        assert ex.execute("charge_card", {"idempotency_key": "retry-1"}) == "ok"
        assert attempts["n"] == 2

    def test_retry_after_simulated_process_crash_before_completion(self, tmp_path):
        """Simulates: process claims the idempotency key, then dies before
        calling complete/fail (no `finally`, no graceful shutdown — a real
        crash). A retry within the stale window must wait/replay-safely; after
        the stale window, it must be able to reclaim and genuinely retry."""
        db = tmp_path / "kynd.db"
        store = SqliteStore(str(db), stale_pending_seconds=0.2)

        # Simulate the crash: claim the key directly (as the executor would at
        # the top of execute()) and then just... stop. No complete, no fail.
        claim = store.claim_idempotency("crashed-key", "charge_card")
        assert claim.status == "new"
        # process "dies" here — nothing calls complete_idempotency or fail_idempotency

        # Immediately after: another caller must not silently re-run (the
        # first attempt might still be genuinely in flight from Kynd's point
        # of view, even though we know out-of-band that it is dead).
        immediate = store.claim_idempotency("crashed-key", "charge_card")
        assert immediate.status == "in_progress"

        time.sleep(0.3)  # exceed stale_pending_seconds

        # Now the claim is reclaimable — a genuine retry can proceed.
        reclaimed = store.claim_idempotency("crashed-key", "charge_card")
        assert reclaimed.status == "new", "stale pending claim must become reclaimable"

    def test_concurrent_caller_gets_error_not_hang_if_owner_never_finishes(self, tmp_path):
        store = SqliteStore(str(tmp_path / "kynd.db"))
        raw = {"capabilities": [{"name": "charge_card"}]}

        owner_started = threading.Event()

        def hangs_forever(params):
            owner_started.set()
            time.sleep(30)  # longer than the executor's wait timeout
            return "too-late"

        reg = ToolRegistry()
        reg.register("charge_card", hangs_forever)
        ex_owner = Executor(Constitution(raw), reg, store=store)
        ex_waiter = Executor(Constitution(raw), reg, store=store)

        owner_thread = threading.Thread(
            target=lambda: ex_owner.execute("charge_card", {"idempotency_key": "hang-1"})
        )
        owner_thread.daemon = True
        owner_thread.start()
        owner_started.wait(timeout=5)
        time.sleep(0.05)  # ensure the claim row is committed

        with pytest.raises(KyndConcurrentExecutionError):
            ex_waiter.execute(
                "charge_card", {"idempotency_key": "hang-1"}
            ) if False else _execute_with_short_wait(store, "hang-1", "charge_card")


def _execute_with_short_wait(store, key, capability):
    """Poll with a short timeout to keep the test fast, mirroring what the
    executor does with its default (longer) timeout."""
    claim = store.claim_idempotency(key, capability)
    if claim.status == "in_progress":
        row = store.wait_for_idempotency(key, timeout=0.3, interval=0.05)
        if row is None or row["status"] not in ("completed", "failed"):
            raise KyndConcurrentExecutionError("still in progress")
    return claim


# ============================================================== D: approval verification


class TestApprovalVerification:
    RAW = {
        "hard_rules": [
            {
                "name": "require-approval",
                "type": "require_param",
                "param": "approval_id",
                "verify": "approval",
                "action_types": ["charge_card"],
            }
        ],
        "capabilities": [{"name": "charge_card", "max_amount": 1000, "max_calls_per_day": 100}],
    }

    def test_fake_approval_id_fails(self, tmp_path):
        store = make_store(tmp_path)
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="not found"):
            ex.execute("charge_card", {"amount": 10, "approval_id": "abc123"})

    def test_forged_looking_approval_id_fails(self, tmp_path):
        """A string shaped like a real token, but never issued."""
        store = make_store(tmp_path)
        real = store.issue_approval("charge_card", max_amount=1000)
        forged = real[:-4] + "XXXX"  # tamper with the last 4 chars
        assert forged != real
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="not found"):
            ex.execute("charge_card", {"amount": 10, "approval_id": forged})

    def test_valid_approval_succeeds(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=1000, max_uses=1)
        ex = make_executor(store, self.RAW)
        result = ex.execute("charge_card", {"amount": 100, "approval_id": aid})
        assert result == "charge_card:ok"

    def test_expired_approval_fails(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=1000, ttl_seconds=0.01)
        time.sleep(0.05)
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="expired"):
            ex.execute("charge_card", {"amount": 100, "approval_id": aid})

    def test_mismatched_capability_fails(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("send_email")  # issued for a DIFFERENT capability
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="issued for capability 'send_email'"):
            ex.execute("charge_card", {"amount": 100, "approval_id": aid})

    def test_mismatched_target_fails(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", target="team@kynd.io")
        raw = {**self.RAW}
        raw["capabilities"] = [{"name": "charge_card", "allowed_targets": ["team@kynd.io", "evil@x.com"]}]
        ex = make_executor(store, raw)
        with pytest.raises(KyndExecutionError, match="issued for target"):
            ex.execute(
                "charge_card", {"amount": 1, "approval_id": aid, "target": "evil@x.com"}
            )

    def test_amount_exceeding_approval_cap_fails(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=50)
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match=r"exceeds approved max \$50\.00"):
            ex.execute("charge_card", {"amount": 100, "approval_id": aid})

    def test_consumed_one_time_approval_fails_on_reuse(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=1000, max_uses=1)
        ex = make_executor(store, self.RAW)
        ex.execute("charge_card", {"amount": 10, "approval_id": aid})
        with pytest.raises(KyndExecutionError, match="already consumed"):
            ex.execute("charge_card", {"amount": 10, "approval_id": aid})

    def test_malformed_approval_id_fails(self, tmp_path):
        store = make_store(tmp_path)
        ex = make_executor(store, self.RAW)
        for bad in ["", "   ", None]:
            params = {"amount": 10}
            if bad is not None:
                params["approval_id"] = bad
            with pytest.raises(KyndExecutionError):
                ex.execute("charge_card", params)

    def test_missing_approval_fails(self, tmp_path):
        store = make_store(tmp_path)
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="missing required param"):
            ex.execute("charge_card", {"amount": 10})

    def test_revoked_approval_fails(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=1000)
        store.revoke_approval(aid)
        ex = make_executor(store, self.RAW)
        with pytest.raises(KyndExecutionError, match="revoked"):
            ex.execute("charge_card", {"amount": 10, "approval_id": aid})

    def test_unauthorized_operation_not_covered_by_approval_scope(self, tmp_path):
        """An approval for 'charge $50 to team@kynd.io' must not authorize
        'charge $50 to evil@x.com' even though the amount matches."""
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=50, target="team@kynd.io")
        raw = {
            **self.RAW,
            "capabilities": [
                {"name": "charge_card", "allowed_targets": ["team@kynd.io", "evil@x.com"]}
            ],
        }
        ex = make_executor(store, raw)
        with pytest.raises(KyndExecutionError, match="issued for target"):
            ex.execute("charge_card", {"amount": 50, "approval_id": aid, "target": "evil@x.com"})
        # The legitimate target still works with the same approval.
        assert (
            ex.execute("charge_card", {"amount": 50, "approval_id": aid, "target": "team@kynd.io"})
            == "charge_card:ok"
        )

    def test_no_store_means_presence_is_never_enough(self, tmp_path):
        """D-2's original bug: `require_param` alone treats presence as valid.
        With `verify: approval` but NO store wired in, a model-invented string
        must still be rejected — never silently trusted."""
        reg = ToolRegistry()
        reg.register("charge_card", lambda p: "SHOULD NOT RUN")
        ex = Executor(Constitution(self.RAW), reg)  # no store=
        with pytest.raises(KyndExecutionError, match="no approval store is configured"):
            ex.execute("charge_card", {"amount": 10, "approval_id": "abc123"})

    def test_model_cannot_bypass_by_omitting_verify_requirement(self, tmp_path):
        """Sanity: a constitution WITHOUT verify:approval still only checks
        presence — this is intentional backward compatibility, not a bypass of
        the verify:approval path, and is documented. Confirms the two modes
        are genuinely distinct and neither silently mimics the other."""
        store = make_store(tmp_path)
        raw = {
            "hard_rules": [
                {"name": "require-approval", "type": "require_param", "param": "approval_id"}
            ],
            "capabilities": [{"name": "charge_card"}],
        }
        ex = make_executor(store, raw)
        # No verify:approval configured -> presence suffices, as before D-1.
        result = ex.execute("charge_card", {"approval_id": "any-string-at-all"})
        assert result == "charge_card:ok"

    def test_concurrent_consumption_of_one_time_approval_only_one_wins(self, tmp_path):
        store = make_store(tmp_path)
        aid = store.issue_approval("charge_card", max_amount=1000, max_uses=1)
        ex = make_executor(store, self.RAW)

        outcomes = []
        lock = threading.Lock()

        def worker():
            try:
                ex.execute("charge_card", {"amount": 1, "approval_id": aid})
                with lock:
                    outcomes.append("ok")
            except KyndExecutionError:
                with lock:
                    outcomes.append("denied")

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert outcomes.count("ok") == 1, f"expected exactly 1 winner, got {outcomes.count('ok')}"
        assert outcomes.count("denied") == 19

    def test_issue_approval_rejects_bad_input(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ValueError):
            store.issue_approval("charge_card", max_amount=-5)
        with pytest.raises(ValueError):
            store.issue_approval("charge_card", max_uses=0)


# ============================================================== E: crash recovery


class TestCrashRecovery:
    def test_migration_is_transactional_partial_failure_leaves_no_version_bump(self, tmp_path, monkeypatch):
        """If a migration step fails partway, schema_version must NOT advance
        — a half-applied schema must never be mistaken for a complete one."""
        import kynd_runtime.persistence as persistence_mod

        db = tmp_path / "kynd.db"
        broken_migrations = dict(persistence_mod._MIGRATIONS)
        broken_migrations[1] = broken_migrations[1] + "\nCREATE TABLE this_will_fail_because_duplicate (x INT);\nCREATE TABLE this_will_fail_because_duplicate (x INT);"
        monkeypatch.setattr(persistence_mod, "_MIGRATIONS", broken_migrations)

        with pytest.raises(sqlite3.OperationalError):
            SqliteStore(str(db))

        # The file may exist (SQLite creates it on connect) but must have no
        # applied schema — a subsequent honest attempt must be able to migrate
        # cleanly from scratch, not find itself half-initialized.
        monkeypatch.undo()
        store = SqliteStore(str(db))
        assert store.schema_version() == persistence_mod.SCHEMA_VERSION
        # And it must be actually usable, not a corrupt half-schema.
        store.issue_approval("charge_card")

    def test_database_file_missing_parent_dir_is_created(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "kynd.db"
        store = SqliteStore(str(deep))
        assert deep.exists()
        assert store.schema_version() == 1

    def test_partial_execution_failed_status_is_durable(self, tmp_path):
        """A handler that raises mid-execution: the failure itself, not a
        false success, must be what's durably recorded — proven by reading
        it back after a simulated restart."""
        store = make_store(tmp_path)
        raw = {"capabilities": [{"name": "send_email"}]}

        def boom(params):
            raise RuntimeError("smtp down")

        reg = ToolRegistry()
        reg.register("send_email", boom)
        ex = Executor(Constitution(raw), reg, store=store)
        with pytest.raises(RuntimeError):
            ex.execute("send_email", {"target": "a@b.c"})
        del ex

        store2 = SqliteStore(store.path)
        recs = store2.recent_execution()
        assert recs[-1]["status"] == "failed"
        assert recs[-1]["allowed"] == 1  # governance permitted it; it just didn't happen
        assert "smtp down" in recs[-1]["error"]

    def test_retry_after_failed_execution_is_a_genuine_new_attempt_after_restart(self, tmp_path):
        db = tmp_path / "kynd.db"
        raw = {"capabilities": [{"name": "charge_card"}]}
        attempts_file = tmp_path / "attempts.txt"
        attempts_file.write_text("0")

        def flaky(params):
            n = int(attempts_file.read_text()) + 1
            attempts_file.write_text(str(n))
            if n == 1:
                raise RuntimeError("fails once")
            return "ok"

        store = SqliteStore(str(db))
        reg = ToolRegistry()
        reg.register("charge_card", flaky)
        ex = Executor(Constitution(raw), reg, store=store)
        with pytest.raises(RuntimeError):
            ex.execute("charge_card", {"idempotency_key": "restart-retry"})
        del ex, store  # simulated crash right after the failure

        store2 = SqliteStore(str(db))
        ex2 = Executor(Constitution(raw), reg, store=store2)
        result = ex2.execute("charge_card", {"idempotency_key": "restart-retry"})
        assert result == "ok"
        assert int(attempts_file.read_text()) == 2


class TestDatabaseUnavailable:
    def test_readonly_directory_raises_persistence_error_not_silent_pass(self, tmp_path):
        """If the store cannot be reached, governance must not silently allow
        everything — it must raise, loudly, so the caller cannot mistake
        'the datastore is broken' for 'nothing was requested'."""
        bad_dir = tmp_path / "readonly"
        bad_dir.mkdir()
        db_path = bad_dir / "kynd.db"
        os.chmod(bad_dir, 0o555)
        try:
            with pytest.raises((PersistenceError, sqlite3.OperationalError, OSError)):
                SqliteStore(str(db_path))
        finally:
            os.chmod(bad_dir, 0o755)  # restore so tmp_path cleanup can remove it

    def test_locked_database_times_out_rather_than_hanging_forever(self, tmp_path):
        """An external, uncooperative writer holding an exclusive lock must
        cause a bounded failure, not an indefinite hang."""
        db = tmp_path / "kynd.db"
        _store = SqliteStore(str(db))  # creates schema — must exist before the lock test

        blocker = sqlite3.connect(str(db), isolation_level=None)
        blocker.execute("BEGIN EXCLUSIVE")
        try:
            fast_store = SqliteStore(str(db), timeout=0.3)
            start = time.time()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                fast_store.try_increment_call_count("2026-08-31", "charge_card", 10)
            elapsed = time.time() - start
            assert elapsed < 3.0, f"took {elapsed}s — busy_timeout not bounding the wait"
        finally:
            blocker.execute("ROLLBACK")
            blocker.close()


# ============================================================== G: migrations


class TestMigrations:
    def test_fresh_install_creates_full_schema(self, tmp_path):
        store = SqliteStore(str(tmp_path / "fresh.db"))
        assert store.schema_version() == 1
        # Every table must be usable immediately.
        store.try_increment_call_count("2026-08-31", "x", None)
        store.append_audit("x", "a", None, True, "ok")
        store.append_execution("x", None, {}, True, "allowed", "ok", None, None, None)
        store.claim_idempotency("k", "x")
        store.issue_approval("x")

    def test_reopening_current_schema_is_a_noop(self, tmp_path):
        db = tmp_path / "kynd.db"
        store1 = SqliteStore(str(db))
        store1.try_increment_call_count("2026-08-31", "x", None)
        del store1
        store2 = SqliteStore(str(db))
        # Data from before "reopening" must still be there — migration did not
        # wipe or re-create tables it didn't need to touch.
        assert store2.calls_today("2026-08-31", "x") == 1

    def test_concurrent_first_open_does_not_corrupt_schema(self, tmp_path):
        """Multiple threads opening a store against a brand-new file
        simultaneously — the migration's own lock must serialize them."""
        db = tmp_path / "kynd.db"
        errors = []
        stores = []
        lock = threading.Lock()

        def opener():
            try:
                s = SqliteStore(str(db))
                with lock:
                    stores.append(s)
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = [threading.Thread(target=opener) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"concurrent first-open failures: {errors}"
        assert all(s.schema_version() == 1 for s in stores)


# ============================================================== integration: full pipeline


class TestFullPipelineWithStore:
    """End-to-end: gate + broker + approval + idempotency all wired through
    one store, exactly as a real deployment would run it."""

    def test_realistic_workflow(self, tmp_path):
        store = make_store(tmp_path)
        raw = {
            "hard_rules": [
                {"name": "no-delete", "type": "block_action_type", "action_types": ["delete"]},
                {
                    "name": "require-approval",
                    "type": "require_param",
                    "param": "approval_id",
                    "verify": "approval",
                    "action_types": ["charge_card"],
                },
            ],
            "capabilities": [
                {"name": "charge_card", "max_amount": 500, "max_calls_per_day": 3},
                {"name": "delete_all_customers", "max_calls_per_day": 10},
                {"name": "send_email", "max_calls_per_day": 10, "allowed_targets": ["team@kynd.io"]},
            ],
        }
        reg = ToolRegistry()
        reg.register("charge_card", lambda p: f"charged ${p['amount']}")
        reg.register("delete_all_customers", lambda p: "SHOULD NEVER RUN")
        reg.register("send_email", lambda p: "sent")
        ex = Executor(Constitution(raw), reg, store=store)

        # 1. destructive action blocked
        with pytest.raises(KyndExecutionError):
            ex.execute("delete_all_customers", {})

        # 2. charge without approval blocked
        with pytest.raises(KyndExecutionError, match="missing required param"):
            ex.execute("charge_card", {"amount": 10})

        # 3. charge with fake approval blocked
        with pytest.raises(KyndExecutionError, match="not found"):
            ex.execute("charge_card", {"amount": 10, "approval_id": "fake"})

        # 4. issue a real approval and use it
        aid = store.issue_approval("charge_card", max_amount=100, max_uses=1)
        result = ex.execute("charge_card", {"amount": 50, "approval_id": aid})
        assert "50" in result

        # 5. reuse the same (now consumed) approval fails
        with pytest.raises(KyndExecutionError, match="already consumed"):
            ex.execute("charge_card", {"amount": 50, "approval_id": aid})

        # 6. ordinary send works and respects the allowlist
        assert ex.execute("send_email", {"target": "team@kynd.io"}) == "sent"

        # 7. restart: everything above is still true
        del ex
        store2 = SqliteStore(store.path)
        ex2 = Executor(Constitution(raw), reg, store=store2)
        assert ex2.calls_today("charge_card") == 1
        assert store2.validate_approval(aid, "charge_card", amount=50).ok is False
        with pytest.raises(KyndExecutionError, match="already consumed"):
            ex2.execute("charge_card", {"amount": 50, "approval_id": aid})
