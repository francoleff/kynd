"""Durable governance state — SQLite-backed store for caps, audit, idempotency,
and approvals.

Why SQLite and not a new service: the deployment model documented in
RELEASE_PLAN.md is a single-host library, optionally fronted by one loopback
webhook process. SQLite with WAL mode plus ``BEGIN IMMEDIATE`` transactions
gives real atomic cross-process coordination on that model without adding a
network service, a new runtime dependency, or an operational component nobody
asked for. It is stdlib. If Kynd ever needs true multi-host coordination, that
is a different deployment model and a different decision — not something to
speculatively build today.

What this module owns:
    - daily call counts, keyed by (UTC date, capability), incremented atomically
    - the audit log (every broker attempt, allow or deny)
    - the execution log (every executor attempt, allowed/denied/failed)
    - idempotency claims, so a retried request cannot double-execute
    - approval records, with a real lifecycle (issue -> validate -> consume)

Concurrency model:
    Every write path opens a short-lived connection, takes ``BEGIN IMMEDIATE``
    (SQLite's write lock, acquired eagerly rather than on first write), performs
    the check-and-mutate as one transaction, and commits or rolls back. Two
    processes racing for the same row serialize on that lock: the loser's
    ``BEGIN IMMEDIATE`` blocks until the winner commits, then re-evaluates the
    WHERE clause against the now-current row. This is what makes quota
    increments, idempotency claims, and approval consumption safe across
    processes, not just across threads in one process.

Honesty about limits — read before assuming more than this provides:
    - This is single-host coordination. It assumes every process sees the same
      file (a local disk or a shared network volume with correct locking
      semantics — NFS is famously not that; do not put the DB there).
    - Exactly-once EXTERNAL side effects are not achievable here and this
      module does not claim them. The tool handler's real work (an SMTP send,
      a card charge) happens outside any transaction Kynd controls. If a
      process dies between "handler ran" and "result recorded," a retry after
      restart will re-invoke the handler. See ``STALE_PENDING_SECONDS`` below
      and docs/engineering/RELIABILITY_AUDIT.md R-1 / R-3 for the full
      statement of this limitation. What IS guaranteed: governance decisions
      (caps, approvals) are never double-consumed, and a given idempotency key
      converges on one recorded outcome that every caller observes.
"""

from __future__ import annotations

import json
import logging
import numbers
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# A "pending" idempotency claim older than this is treated as abandoned (the
# process that claimed it is presumed dead) and becomes reclaimable. This is
# the practical bound on "stuck forever" — see the module docstring's honesty
# note about what this does and does not guarantee.
DEFAULT_STALE_PENDING_SECONDS = 300.0

# How long a caller will poll for a concurrent duplicate request to finish
# before giving up and raising.
DEFAULT_IDEMPOTENCY_WAIT_SECONDS = 10.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.05

SCHEMA_VERSION = 1

_MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS call_counts (
            day TEXT NOT NULL,
            capability TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day, capability)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            capability TEXT NOT NULL,
            action TEXT NOT NULL,
            amount REAL,
            allowed INTEGER NOT NULL,
            reason TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execution_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            capability TEXT NOT NULL,
            action_type TEXT,
            params_json TEXT NOT NULL,
            allowed INTEGER NOT NULL,
            status TEXT NOT NULL,
            reason TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            idempotency_key TEXT
        );

        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key TEXT PRIMARY KEY,
            capability TEXT NOT NULL,
            status TEXT NOT NULL,
            result_json TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            capability TEXT NOT NULL,
            action_type TEXT,
            max_amount REAL,
            target TEXT,
            max_uses INTEGER,
            use_count INTEGER NOT NULL DEFAULT 0,
            issued_at REAL NOT NULL,
            expires_at REAL,
            revoked INTEGER NOT NULL DEFAULT 0,
            issued_by TEXT,
            last_consumed_at REAL,
            last_consumed_by_key TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_audit_log_ts ON audit_log(ts);
        CREATE INDEX IF NOT EXISTS idx_execution_log_ts ON execution_log(ts);
    """,
}


def _split_sql_statements(script: str) -> list[str]:
    """Split a migration script into individual statements on ';'.

    Safe for the migrations defined in this module because none of them
    contain a semicolon inside a string literal or identifier. Not a general
    SQL parser — do not reuse for arbitrary user-supplied SQL.
    """
    return [s.strip() for s in script.split(";") if s.strip()]


def _safe_rollback(conn: sqlite3.Connection) -> None:
    """ROLLBACK, tolerating "no transaction is active".

    Used in except-blocks after a BEGIN IMMEDIATE that may itself have been
    the thing that raised (e.g. a lock timeout) — in that case there is
    nothing to roll back, and calling ROLLBACK unconditionally raises a
    second, more confusing OperationalError that masks the original one.
    Confirmed by a test that holds an external exclusive lock against the
    file and asserts on the *original* error.
    """
    try:
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError:
        pass


class PersistenceError(Exception):
    """Raised for store-level failures (corrupt schema, unreadable DB, etc.)."""


@dataclass
class ApprovalCheck:
    """Result of validating or consuming an approval."""

    ok: bool
    reason: str


@dataclass
class IdemClaim:
    """Result of attempting to claim an idempotency key.

    status:
        "new"         — caller owns this key; must execute and then call
                        complete_idempotency() or fail_idempotency()
        "completed"   — a prior attempt finished; `result` holds the cached value
        "in_progress" — another attempt (possibly another process) is running;
                        caller should poll wait_for_idempotency()
        "conflict"    — the key was already used for a different capability
    """

    status: str
    result: Any = None
    capability: str | None = None


def _json_safe(value: Any) -> str:
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


class SqliteStore:
    """Durable governance state shared across processes via a SQLite file.

    One store per DB file. Safe to construct from multiple processes pointed
    at the same path — schema migration is itself run under a write lock, so
    concurrent startup does not race the migration.
    """

    def __init__(
        self,
        path: str | Path,
        timeout: float = 30.0,
        stale_pending_seconds: float = DEFAULT_STALE_PENDING_SECONDS,
    ) -> None:
        self.path = str(path)
        self._timeout = timeout
        self._stale_pending_seconds = stale_pending_seconds
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    # -- connection lifecycle -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        # Retried: the very first WAL-mode conversion on a brand-new database
        # file is a distinct exclusive-lock event that can raise "database is
        # locked" even with busy_timeout set, if multiple processes race to
        # create the file for the first time simultaneously. Confirmed by
        # running 8 real OS processes against a fresh DB path at once — one
        # died here on the very first run. Reconnecting is safe: sqlite3.connect
        # itself does not hold any lock, so a fresh attempt starts clean.
        last_error: sqlite3.OperationalError | None = None
        for attempt in range(5):
            try:
                conn = sqlite3.connect(self.path, timeout=self._timeout, isolation_level=None)
                conn.row_factory = sqlite3.Row
                conn.execute(f"PRAGMA busy_timeout={int(self._timeout * 1000)}")
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA foreign_keys=ON")
                return conn
            except sqlite3.OperationalError as e:
                if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                    raise
                last_error = e
                time.sleep(0.02 * (2**attempt))
        raise PersistenceError(
            f"Could not open {self.path!r} after 5 attempts: {last_error}"
        ) from last_error

    def _migrate(self) -> None:
        """Apply any migrations newer than the current schema version.

        Fresh installs: creates the full schema at SCHEMA_VERSION. Existing
        installs: applies only the migrations above the recorded version, in
        order, inside one transaction — a failure rolls back cleanly and the
        recorded version is unchanged, so a partial migration can never be
        mistaken for a complete one.
        """
        conn = self._connect()
        in_transaction = False
        try:
            # Cheap read first, no lock: if we're already current, avoid
            # taking a write lock at all. This also means opening a store
            # against a DB that's already at the latest schema never
            # contends with a concurrent writer — only an actual migration
            # needs BEGIN IMMEDIATE.
            has_version_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            ).fetchone()
            current = 0
            if has_version_table:
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                current = row["version"] if row else 0
            if current >= SCHEMA_VERSION:
                return

            conn.execute("BEGIN IMMEDIATE")
            in_transaction = True
            # Re-read under the write lock: another process may have migrated
            # between our unlocked read above and acquiring this lock.
            has_version_table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            ).fetchone()
            current = 0
            if has_version_table:
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                current = row["version"] if row else 0

            if current >= SCHEMA_VERSION:
                conn.execute("ROLLBACK")
                return

            for version in range(current + 1, SCHEMA_VERSION + 1):
                script = _MIGRATIONS.get(version)
                if script is None:
                    raise PersistenceError(f"No migration registered for schema version {version}")
                # Deliberately NOT conn.executescript(): sqlite3's executescript
                # implicitly COMMITs any open transaction before running, which
                # would break out of our explicit BEGIN IMMEDIATE lock and let a
                # concurrent process's migration interleave with ours. Splitting
                # into individual statements keeps everything inside one atomic
                # transaction.
                for statement in _split_sql_statements(script):
                    conn.execute(statement)

            if current == 0:
                conn.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
            else:
                conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
            conn.execute("COMMIT")
            logger.info("kynd persistence: migrated %s -> schema v%d", self.path, SCHEMA_VERSION)
        except Exception:
            # Only roll back if BEGIN actually succeeded — otherwise ROLLBACK
            # itself raises "no transaction is active" and masks the real
            # error (confirmed: a locked DB at BEGIN IMMEDIATE hit exactly
            # this before the guard was added).
            if in_transaction:
                _safe_rollback(conn)
            raise
        finally:
            conn.close()

    def schema_version(self) -> int:
        conn = self._connect()
        try:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            return row["version"] if row else 0
        finally:
            conn.close()

    def close(self) -> None:
        """No persistent connection is held; provided for symmetry / context-manager use."""

    # -- call counts (daily quota) -------------------------------------------

    def try_increment_call_count(
        self, day: str, capability: str, max_calls: int | None
    ) -> tuple[bool, int]:
        """Atomically check-and-increment a capability's count for ``day``.

        Returns (allowed, count_after_this_call_if_allowed_else_current_count).
        A denied call does NOT increment — quota is only consumed by requests
        that are actually permitted, matching the broker's existing contract.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT count FROM call_counts WHERE day = ? AND capability = ?",
                (day, capability),
            ).fetchone()
            current = row["count"] if row else 0

            if max_calls is not None and current >= max_calls:
                conn.execute("ROLLBACK")
                return False, current

            new_count = current + 1
            conn.execute(
                "INSERT INTO call_counts(day, capability, count) VALUES (?, ?, ?) "
                "ON CONFLICT(day, capability) DO UPDATE SET count = excluded.count",
                (day, capability, new_count),
            )
            conn.execute("COMMIT")
            return True, new_count
        except Exception:
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    def calls_today(self, day: str, capability: str) -> int:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT count FROM call_counts WHERE day = ? AND capability = ?",
                (day, capability),
            ).fetchone()
            return row["count"] if row else 0
        finally:
            conn.close()

    def reset_daily_counts(self, day: str | None = None) -> None:
        """Clear call counts. All days if ``day`` is None (operator override)."""
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if day is None:
                conn.execute("DELETE FROM call_counts")
            else:
                conn.execute("DELETE FROM call_counts WHERE day = ?", (day,))
            conn.execute("COMMIT")
        except Exception:
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    # -- audit log ------------------------------------------------------------

    def append_audit(
        self, capability: str, action: str, amount: float | None, allowed: bool, reason: str
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO audit_log(ts, capability, action, amount, allowed, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), capability, action, amount, 1 if allowed else 0, reason),
            )
            return cur.lastrowid or 0
        finally:
            conn.close()

    def recent_audit(self, limit: int = 10_000) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM audit_log ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (limit,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()

    # -- execution log ---------------------------------------------------------

    def append_execution(
        self,
        capability: str,
        action_type: str | None,
        params: dict[str, Any],
        allowed: bool,
        status: str,
        reason: str,
        result: Any,
        error: str | None,
        idempotency_key: str | None,
    ) -> int:
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT INTO execution_log "
                "(ts, capability, action_type, params_json, allowed, status, reason, "
                " result_json, error, idempotency_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    time.time(),
                    capability,
                    action_type,
                    _json_safe(params),
                    1 if allowed else 0,
                    status,
                    reason,
                    _json_safe(result) if result is not None else None,
                    error,
                    idempotency_key,
                ),
            )
            return cur.lastrowid or 0
        finally:
            conn.close()

    def recent_execution(self, limit: int = 10_000) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM execution_log ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (limit,),
            ).fetchall()
            out = []
            for r in rows:
                d = _row_to_dict(r)
                d["params"] = json.loads(d.pop("params_json"))
                result_json = d.pop("result_json")
                d["result"] = json.loads(result_json) if result_json is not None else None
                out.append(d)
            return out
        finally:
            conn.close()

    # -- idempotency ------------------------------------------------------------

    def claim_idempotency(self, key: str, capability: str) -> IdemClaim:
        """Attempt to become the owner of ``key``.

        See module docstring for the crash-recovery honesty note: a claim that
        is "in_progress" because its owning process crashed becomes reclaimable
        only after ``stale_pending_seconds``. Before that window elapses a
        retry will correctly wait rather than duplicate; after it elapses a
        retry may re-invoke a handler whose side effect already happened. That
        boundary is inherent to coordinating an external, non-transactional
        side effect and is documented, not hidden.
        """
        conn = self._connect()
        try:
            now = time.time()
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO idempotency_keys(key, capability, status, created_at, updated_at) "
                    "VALUES (?, ?, 'pending', ?, ?)",
                    (key, capability, now, now),
                )
                conn.execute("COMMIT")
                return IdemClaim(status="new")
            except sqlite3.IntegrityError:
                conn.execute("ROLLBACK")

            row = conn.execute(
                "SELECT * FROM idempotency_keys WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                # Row vanished between the failed insert and this read — race
                # with a concurrent claim; caller can safely retry the whole
                # claim from scratch.
                return IdemClaim(status="in_progress")

            if row["capability"] != capability:
                return IdemClaim(status="conflict", capability=row["capability"])

            if row["status"] == "completed":
                return IdemClaim(
                    status="completed",
                    result=json.loads(row["result_json"]) if row["result_json"] is not None else None,
                )

            # "failed" or a "pending" claim stale enough to presume abandoned:
            # both are reclaimable by the next caller.
            reclaimable = row["status"] == "failed" or (
                row["status"] == "pending"
                and (now - row["updated_at"]) > self._stale_pending_seconds
            )
            if reclaimable:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.execute(
                    "UPDATE idempotency_keys SET status = 'pending', updated_at = ? "
                    "WHERE key = ? AND status = ?",
                    (now, key, row["status"]),
                )
                if cur.rowcount == 1:
                    conn.execute("COMMIT")
                    return IdemClaim(status="new")
                conn.execute("ROLLBACK")
                # Someone else reclaimed it in the gap; fall through to poll.

            return IdemClaim(status="in_progress")
        finally:
            conn.close()

    def complete_idempotency(self, key: str, result: Any) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE idempotency_keys SET status = 'completed', result_json = ?, "
                "error = NULL, updated_at = ? WHERE key = ?",
                (_json_safe(result), time.time(), key),
            )
        finally:
            conn.close()

    def fail_idempotency(self, key: str, error: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE idempotency_keys SET status = 'failed', error = ?, "
                "updated_at = ? WHERE key = ?",
                (error, time.time(), key),
            )
        finally:
            conn.close()

    def get_idempotency(self, key: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM idempotency_keys WHERE key = ?", (key,)).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def wait_for_idempotency(
        self,
        key: str,
        timeout: float = DEFAULT_IDEMPOTENCY_WAIT_SECONDS,
        interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
    ) -> Optional[dict[str, Any]]:
        """Poll until ``key`` reaches a terminal state or ``timeout`` elapses."""
        deadline = time.time() + timeout
        while True:
            row = self.get_idempotency(key)
            if row is not None and row["status"] in ("completed", "failed"):
                return row
            if time.time() >= deadline:
                return row
            time.sleep(interval)

    # -- approvals --------------------------------------------------------------

    def issue_approval(
        self,
        capability: str,
        action_type: str | None = None,
        max_amount: float | None = None,
        target: str | None = None,
        ttl_seconds: float | None = 3600.0,
        max_uses: int | None = 1,
        issued_by: str | None = None,
    ) -> str:
        """Issue a new approval and return its unguessable token.

        ``max_uses=1`` (the default) is one-time-use semantics. ``max_uses=None``
        means unlimited uses until expiry — for a human approving a batch of
        actions in advance, for example. ``ttl_seconds=None`` never expires;
        use with real caution, and prefer a short TTL for anything money-moving.
        """
        if max_amount is not None:
            if isinstance(max_amount, bool) or not isinstance(max_amount, numbers.Real):
                raise ValueError("max_amount must be a number")
            if max_amount < 0:
                raise ValueError("max_amount must not be negative")
        if max_uses is not None and max_uses < 1:
            raise ValueError("max_uses must be at least 1 when set")

        now = time.time()
        expires_at = now + ttl_seconds if ttl_seconds is not None else None

        conn = self._connect()
        try:
            for _ in range(5):  # astronomically unlikely to ever loop, but handled
                approval_id = secrets.token_urlsafe(32)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute(
                        "INSERT INTO approvals "
                        "(approval_id, capability, action_type, max_amount, target, "
                        " max_uses, use_count, issued_at, expires_at, revoked, issued_by) "
                        "VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 0, ?)",
                        (
                            approval_id,
                            capability,
                            action_type,
                            float(max_amount) if max_amount is not None else None,
                            target,
                            max_uses,
                            now,
                            expires_at,
                            issued_by,
                        ),
                    )
                    conn.execute("COMMIT")
                    return approval_id
                except sqlite3.IntegrityError:
                    conn.execute("ROLLBACK")
                    continue
            raise PersistenceError("Could not generate a unique approval_id after 5 attempts")
        finally:
            conn.close()

    def get_approval(self, approval_id: str) -> Optional[dict[str, Any]]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()

    def revoke_approval(self, approval_id: str) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE approvals SET revoked = 1 WHERE approval_id = ?", (approval_id,)
            )
            conn.execute("COMMIT")
            return cur.rowcount == 1
        except Exception:
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    def validate_approval(
        self,
        approval_id: str,
        capability: str,
        action_type: str | None = None,
        amount: float | None = None,
        target: str | None = None,
    ) -> ApprovalCheck:
        """Read-only check: would ``consume_approval`` currently succeed?

        Used by the governance gate, which must stay side-effect-free — a gate
        check that passes does not guarantee the broker will also allow the
        action, so nothing may be consumed here. The atomic claim happens in
        ``consume_approval``, called by the executor only after every other
        check has passed.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            return self._check(row, capability, action_type, amount, target, now=time.time())
        finally:
            conn.close()

    def consume_approval(
        self,
        approval_id: str,
        capability: str,
        action_type: str | None = None,
        amount: float | None = None,
        target: str | None = None,
        consumed_by_key: str | None = None,
    ) -> ApprovalCheck:
        """Atomically claim one use of an approval. Re-validates everything.

        The immutable fields (capability/action_type/target/max_amount) are
        checked against a plain read — they cannot change after issuance, so
        there is no race there. The mutable fields (use_count/expiry/revoked)
        are checked again inside the same atomic UPDATE's WHERE clause, so two
        concurrent consumers of a one-time approval cannot both win: only the
        UPDATE that actually flips a row is committed.
        """
        conn = self._connect()
        try:
            now = time.time()
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
            ).fetchone()
            static_check = self._check(row, capability, action_type, amount, target, now=now)
            if not static_check.ok:
                return static_check

            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                "UPDATE approvals SET use_count = use_count + 1, last_consumed_at = ?, "
                "last_consumed_by_key = ? WHERE approval_id = ? AND revoked = 0 "
                "AND (expires_at IS NULL OR expires_at > ?) "
                "AND (max_uses IS NULL OR use_count < max_uses)",
                (now, consumed_by_key, approval_id, now),
            )
            if cur.rowcount == 0:
                conn.execute("ROLLBACK")
                fresh = conn.execute(
                    "SELECT * FROM approvals WHERE approval_id = ?", (approval_id,)
                ).fetchone()
                return self._check(fresh, capability, action_type, amount, target, now=now, for_consume=True)
            conn.execute("COMMIT")
            return ApprovalCheck(True, "approval consumed")
        except Exception:
            _safe_rollback(conn)
            raise
        finally:
            conn.close()

    @staticmethod
    def _check(
        row: Optional[sqlite3.Row],
        capability: str,
        action_type: str | None,
        amount: float | None,
        target: str | None,
        now: float,
        for_consume: bool = False,
    ) -> ApprovalCheck:
        if row is None:
            return ApprovalCheck(False, "approval not found")
        if row["revoked"]:
            return ApprovalCheck(False, "approval revoked")
        if row["capability"] != capability:
            return ApprovalCheck(
                False,
                f"approval was issued for capability '{row['capability']}', not '{capability}'",
            )
        if row["action_type"] is not None and action_type is not None and row["action_type"] != action_type:
            return ApprovalCheck(
                False,
                f"approval was issued for action_type '{row['action_type']}', not '{action_type}'",
            )
        if row["target"] is not None and row["target"] != target:
            return ApprovalCheck(
                False, f"approval was issued for target '{row['target']}', not '{target}'"
            )
        if row["max_amount"] is not None:
            if amount is None or isinstance(amount, bool) or not isinstance(amount, numbers.Real):
                return ApprovalCheck(False, "approval requires a numeric amount within its cap")
            if float(amount) > row["max_amount"]:
                return ApprovalCheck(
                    False, f"amount ${amount:.2f} exceeds approved max ${row['max_amount']:.2f}"
                )
        if row["expires_at"] is not None and row["expires_at"] <= now:
            return ApprovalCheck(False, "approval expired")
        if row["max_uses"] is not None and row["use_count"] >= row["max_uses"]:
            reason = "approval already consumed" if row["max_uses"] == 1 else "approval use limit reached"
            return ApprovalCheck(False, reason)
        return ApprovalCheck(True, "approval valid")
