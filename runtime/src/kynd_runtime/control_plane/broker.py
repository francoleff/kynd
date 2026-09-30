"""Broker — capability-gated side effects with caps, audit, and fail-closed behavior."""

from __future__ import annotations

import numbers
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Callable

from .constitution import Constitution

if TYPE_CHECKING:
    from ..persistence import SqliteStore

# Keeping every audit entry forever is a memory leak in a long-lived process.
# This bound is large enough to cover a normal operating day and small enough
# to be safe. When a `store` is supplied this deque is a fast local view only
# — the durable copy lives in SQLite and survives restarts.
DEFAULT_AUDIT_LOG_LIMIT = 10_000


@dataclass
class AuditEntry:
    """A single audit log entry for a broker request."""

    timestamp: float
    capability: str
    action: str
    amount: float | None
    allowed: bool
    reason: str


@dataclass
class BrokerResult:
    """Result of a broker request."""

    allowed: bool
    reason: str
    audit_entry: AuditEntry


class Broker:
    """
    Capability-gated side effects. Register a Capability with a Cap
    (max amount, max calls/day, target allowlist), then exercise it
    only through Broker#request. Fail-closed on anything unregistered
    or over cap. One audit entry per attempt, allow or deny.

    Call counts are keyed by UTC date, so ``max_calls_per_day`` genuinely
    means per day.

    Without a ``store``: counts and audit live in this process's memory only
    — they reset on restart and are not shared across processes. This is the
    original behavior, unchanged, and is what every pre-existing test exercises.

    With a ``store`` (a :class:`kynd_runtime.persistence.SqliteStore`): the
    daily call count becomes the durable, cross-process source of truth —
    the check-and-increment happens as one atomic transaction in SQLite, so
    two processes racing for the last unit of quota cannot both win. Every
    audit entry is also written there. The in-memory deque is kept in both
    modes purely as a fast local view for ``.audit_log``; it is never the
    source of truth for a request's outcome once a store is configured.
    """

    def __init__(
        self,
        constitution: Constitution,
        audit_log_limit: int = DEFAULT_AUDIT_LOG_LIMIT,
        clock: Callable[[], datetime] | None = None,
        store: "SqliteStore | None" = None,
    ) -> None:
        self._constitution = constitution
        self._audit_log: deque[AuditEntry] = deque(maxlen=audit_log_limit)
        # (utc_date, capability) -> calls made that day. Only the source of
        # truth when `store` is None; see class docstring.
        self._call_counts: dict[tuple[date, str], int] = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        # Guards the read-modify-write of _call_counts in the in-memory path.
        # The window between reading a count and incrementing it is a
        # check-then-act race; this closes it for threads within one process.
        # It provides no cross-process protection — that is what `store` is for.
        self._lock = threading.Lock()
        self._store = store

    def request(
        self,
        capability_name: str,
        action: str,
        amount: float | None = None,
        target: str | None = None,
    ) -> BrokerResult:
        """
        Request to exercise a capability. Returns BrokerResult.
        Fail-closed: if anything is unregistered or over cap, deny.
        """
        cap_config = self._constitution.get_capability(capability_name)

        # 1. Capability must be registered
        if cap_config is None:
            return self._deny(
                capability_name, action, amount, f"Unregistered capability: {capability_name}"
            )

        # 2. Amount must be interpretable before it is compared
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, numbers.Real):
                return self._deny(
                    capability_name,
                    action,
                    None,
                    f"Amount must be a number for '{capability_name}', "
                    f"got {type(amount).__name__}",
                )
            amount = float(amount)
            if amount != amount or amount in (float("inf"), float("-inf")):
                return self._deny(
                    capability_name, action, None, f"Amount must be finite for '{capability_name}'"
                )
            if amount < 0:
                return self._deny(
                    capability_name,
                    action,
                    amount,
                    f"Negative amount ${amount:.2f} not permitted for '{capability_name}'",
                )

        # 3. Check max amount per request (strictest of money_caps / max_amount)
        max_amount = self._constitution.effective_max_amount(capability_name)
        if amount is not None and max_amount is not None and amount > max_amount:
            return self._deny(
                capability_name,
                action,
                amount,
                f"Amount ${amount:.2f} exceeds max ${max_amount:.2f} for '{capability_name}'",
            )

        # 4. Check target allowlist
        allowed_targets = cap_config.get("allowed_targets")
        if allowed_targets is not None:
            if target is None:
                return self._deny(
                    capability_name,
                    action,
                    amount,
                    f"Target required for '{capability_name}' (allowlist enforced)",
                )
            if target not in allowed_targets:
                return self._deny(
                    capability_name,
                    action,
                    amount,
                    f"Target '{target}' not in allowlist for '{capability_name}'",
                )

        # 5. Check and claim the daily call quota atomically. This is last so
        #    that quota is only consumed by requests that pass every other
        #    check — a denied request must not burn the caller's budget.
        max_calls = cap_config.get("max_calls_per_day")
        if max_calls is not None:
            today = self._clock().date()
            if self._store is not None:
                allowed_by_store, _count = self._store.try_increment_call_count(
                    today.isoformat(), capability_name, max_calls
                )
                if not allowed_by_store:
                    return self._deny(
                        capability_name,
                        action,
                        amount,
                        f"Capability '{capability_name}' exceeded max calls per day ({max_calls})",
                    )
            else:
                with self._lock:
                    current = self._call_counts.get((today, capability_name), 0)
                    if current >= max_calls:
                        return self._deny(
                            capability_name,
                            action,
                            amount,
                            f"Capability '{capability_name}' exceeded max calls per day ({max_calls})",
                        )
                    self._call_counts[(today, capability_name)] = current + 1
                    self._prune_old_counts(today)

        return self._allow(capability_name, action, amount)

    def _allow(self, capability: str, action: str, amount: float | None) -> BrokerResult:
        entry = AuditEntry(
            timestamp=time.time(),
            capability=capability,
            action=action,
            amount=amount,
            allowed=True,
            reason="Allowed by broker",
        )
        self._audit_log.append(entry)
        if self._store is not None:
            self._store.append_audit(capability, action, amount, True, entry.reason)
        return BrokerResult(allowed=True, reason="Allowed by broker", audit_entry=entry)

    def _deny(
        self, capability: str, action: str, amount: float | None, reason: str
    ) -> BrokerResult:
        """Create a denied result and log it."""
        entry = AuditEntry(
            timestamp=time.time(),
            capability=capability,
            action=action,
            amount=amount,
            allowed=False,
            reason=reason,
        )
        self._audit_log.append(entry)
        if self._store is not None:
            self._store.append_audit(capability, action, amount, False, reason)
        return BrokerResult(allowed=False, reason=reason, audit_entry=entry)

    def _prune_old_counts(self, today: date) -> None:
        """Drop counters for past days so the dict cannot grow without bound.

        Caller must hold ``self._lock``. In-memory path only.
        """
        stale = [key for key in self._call_counts if key[0] != today]
        for key in stale:
            del self._call_counts[key]

    def calls_today(self, capability_name: str) -> int:
        """Calls made against a capability on the current UTC date."""
        today = self._clock().date()
        if self._store is not None:
            return self._store.calls_today(today.isoformat(), capability_name)
        with self._lock:
            return self._call_counts.get((today, capability_name), 0)

    @property
    def audit_log(self) -> list[AuditEntry]:
        """Get the local audit log view (most recent entries, up to the configured limit).

        This is always populated, in both modes. When a ``store`` is
        configured, the durable copy is queryable via ``store.recent_audit()``
        and survives restarts; this property does not.
        """
        return list(self._audit_log)

    def reset_daily_counts(self) -> None:
        """Clear all call counts immediately.

        Counts roll over automatically on UTC date change; this is an explicit
        operator override, not a required cron job.

        With a shared ``store``, this clears call counts for every capability
        in every constitution sharing that store file — it is a store-wide
        reset, not scoped to this broker's constitution. That matches "clear
        the day's quotas" as an operator action; document it to your ops team
        if multiple agents share one database.
        """
        if self._store is not None:
            self._store.reset_daily_counts()
        with self._lock:
            self._call_counts.clear()
