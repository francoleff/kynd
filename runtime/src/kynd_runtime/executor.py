"""Executor — the single entry point for all Kynd-governed tool calls.

Usage:
    executor = Executor(constitution, registry)
    result = executor.execute("send_email", {"target": "user@example.com"})

Flow:
    1. Build an action from capability + explicit-or-inferred action type
    2. Gate checks against constitution (hard rules, money caps, approval validity)
    3. Broker checks capability caps (max calls/day, max amount, allowlist)
    4. Any approvals the gate flagged are atomically consumed
    5. If all of the above pass, dispatch to tool handler
    6. Record the outcome — allowed, denied, or failed — in the execution log

With a ``store`` (see kynd_runtime.persistence.SqliteStore): call counts,
audit, execution log, idempotency claims, and approval consumption are all
durable and shared across every process pointed at the same database file.
Without one: everything is process-local memory, exactly as before — this is
the default and every pre-existing caller is unaffected.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .control_plane.broker import Broker, BrokerResult
from .control_plane.constitution import Constitution
from .control_plane.governance_gate import Action, GateResult, GovernanceGate
from .domain_types import ActionType, CapabilityName
from .tool_registry import ToolRegistry

if TYPE_CHECKING:
    from .persistence import SqliteStore

logger = logging.getLogger(__name__)

DEFAULT_EXECUTION_LOG_LIMIT = 10_000

STATUS_ALLOWED = "allowed"
STATUS_DENIED = "denied"
STATUS_FAILED = "failed"


class KyndExecutionError(Exception):
    """Raised when Kynd blocks an action at the gate or broker level."""


class KyndConcurrentExecutionError(Exception):
    """Raised when a duplicate in-flight request could not be resolved.

    Occurs when a concurrent request shares an idempotency key with one that
    is currently executing, and it does not finish within the poll timeout.
    The original request is unaffected; this is purely about how long the
    duplicate caller is willing to wait for its answer.
    """


@dataclass
class ExecutionRecord:
    """A single execution attempt through the Kynd executor.

    ``allowed`` means governance permitted the action. It does NOT mean the
    action succeeded — check ``status`` for that. An audit reader must be able
    to tell a completed charge from a failed one.
    """

    timestamp: float
    capability: str
    params: dict[str, Any]
    allowed: bool
    reason: str
    result: Any = None
    status: str = STATUS_ALLOWED
    action_type: str | None = None
    error: str | None = None
    idempotency_key: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_ALLOWED


class Executor:
    """Governed tool execution: constitution → gate → broker → tool → audit."""

    def __init__(
        self,
        constitution: Constitution,
        registry: ToolRegistry,
        execution_log_limit: int = DEFAULT_EXECUTION_LOG_LIMIT,
        store: "SqliteStore | None" = None,
    ) -> None:
        self._constitution = constitution
        self._registry = registry
        self._store = store
        self._gate = GovernanceGate(constitution, approval_store=store)
        self._broker = Broker(constitution, store=store)
        self._execution_log: deque[ExecutionRecord] = deque(maxlen=execution_log_limit)
        # In-memory fallback only; ignored once a store is configured (the
        # store is the source of truth for idempotency in that mode — see
        # _claim_idempotency / _finish_idempotency below).
        self._idempotency: dict[str, tuple[str, Any]] = {}

    def execute(
        self,
        capability: str,
        params: dict[str, Any],
        action_type: str | None = None,
    ) -> Any:
        """Execute a capability through the full governance pipeline.

        Args:
            capability: The capability name (must be registered in constitution + registry)
            params: Parameters to pass to the tool handler
            action_type: Semantic kind of the action (``delete``, ``charge``,
                ``send``) used to match ``block_action_type`` rules. Defaults to
                the capability name.

        Returns:
            The result from the tool handler

        Raises:
            KyndExecutionError: If the action is blocked by gate or broker,
                or an approval it required could not be consumed
            KyndConcurrentExecutionError: A duplicate request under the same
                idempotency key did not resolve within the poll timeout
            ToolNotFoundError: If no handler is registered for this capability
        """
        if not isinstance(params, dict):
            raise TypeError(f"params must be a dict, got {type(params).__name__}")

        resolved_type = action_type or capability
        amount = params.get("amount")
        target = params.get("target")
        idem_key = params.get("idempotency_key")
        if idem_key is not None and not isinstance(idem_key, str):
            raise TypeError(
                f"idempotency_key must be a string, got {type(idem_key).__name__}"
            )

        # 0. Idempotency: a repeated key returns the prior result without
        #    re-invoking the handler or re-consuming quota. With a store this
        #    claim is atomic and cross-process; a concurrent duplicate blocks
        #    behind the DB write lock rather than racing in memory.
        if idem_key is not None:
            resolved = self._try_resolve_via_idempotency(idem_key, capability, resolved_type, params)
            if resolved is not _NOT_RESOLVED:
                return resolved

        # 1. Build action. The two NewType() calls below are the exact
        #    boundary the F-1 defect crossed: `resolved_type` and
        #    `capability` are both plain strings up to this line, and a
        #    future edit that transposes them here would previously compile
        #    silently. Wrapping each in its own domain type makes that swap
        #    a mypy error (see domain_types.py's module docstring).
        action = Action(
            type=ActionType(resolved_type),
            capability=CapabilityName(capability),
            params=params,
            amount=amount,
        )

        # 2. Gate check (constitution: hard rules, money caps, approval validity)
        gate_result: GateResult = self._gate.check(action)
        if not gate_result.allowed:
            self._deny_and_record(capability, params, gate_result.reason, resolved_type, idem_key)
            raise KyndExecutionError(gate_result.reason)

        # 3. Broker check (capability caps: max calls, max amount, allowlist)
        broker_result: BrokerResult = self._broker.request(
            capability_name=capability,
            action=resolved_type,
            amount=amount,
            target=target,
        )
        if not broker_result.allowed:
            self._deny_and_record(capability, params, broker_result.reason, resolved_type, idem_key)
            raise KyndExecutionError(broker_result.reason)

        # 4. Atomically consume any approvals this action required. Gate check
        #    above only verified they WOULD pass; this is the actual one-time
        #    claim. Must happen after every allow-path check and before the
        #    handler runs, so a denied action never burns an approval and a
        #    handler never runs on an approval that turned out unconsumable
        #    (e.g. a concurrent request already used a one-time approval).
        approvals_needed = self._gate.approvals_to_consume(action)
        consumed: list[str] = []
        try:
            for rule_name, _param_name, approval_id in approvals_needed:
                if self._store is None:
                    # Gate already denied this case (no store => no verify
                    # possible), so this branch is unreachable in practice;
                    # kept as an explicit fail-closed guard, not a silent skip.
                    raise KyndExecutionError(
                        f"Hard rule '{rule_name}': approval verification required "
                        f"but no approval store is configured"
                    )
                result = self._store.consume_approval(
                    approval_id,
                    capability=capability,
                    action_type=resolved_type,
                    amount=amount,
                    target=target,
                    consumed_by_key=idem_key,
                )
                if not result.ok:
                    raise KyndExecutionError(f"Hard rule '{rule_name}': {result.reason}")
                consumed.append(approval_id)
        except KyndExecutionError as e:
            self._deny_and_record(capability, params, str(e), resolved_type, idem_key)
            self._finish_idempotency_failure(idem_key, str(e))
            raise

        # 5. Dispatch to tool handler
        try:
            result = self._registry.call(capability, params)
        except Exception as e:
            # Governance permitted it, but it did not happen. Record both facts
            # separately so the audit trail cannot be misread as a success.
            self._record(
                capability=capability,
                params=params,
                allowed=True,
                reason=f"Tool execution failed: {e}",
                result=None,
                status=STATUS_FAILED,
                action_type=resolved_type,
                error=f"{type(e).__name__}: {e}",
                idempotency_key=idem_key,
            )
            self._finish_idempotency_failure(idem_key, f"{type(e).__name__}: {e}")
            logger.exception("Tool execution failed for capability=%s", capability)
            raise

        # 6. Record success
        self._finish_idempotency_success(idem_key, capability, result)
        self._record(
            capability=capability,
            params=params,
            allowed=True,
            reason="Executed successfully",
            result=result,
            status=STATUS_ALLOWED,
            action_type=resolved_type,
            idempotency_key=idem_key,
        )

        return result

    # -- idempotency ------------------------------------------------------------

    def _try_resolve_via_idempotency(
        self, idem_key: str, capability: str, resolved_type: str, params: dict[str, Any]
    ) -> Any:
        """Returns the cached result if this key is already terminally resolved,
        or ``_NOT_RESOLVED`` if the caller should proceed to execute normally.

        Raises KyndExecutionError / KyndConcurrentExecutionError as appropriate.
        """
        if self._store is not None:
            claim = self._store.claim_idempotency(idem_key, capability)
            if claim.status == "conflict":
                raise KyndExecutionError(
                    f"idempotency_key {idem_key!r} was already used for capability "
                    f"'{claim.capability}'; refusing to reuse it for '{capability}'"
                )
            if claim.status == "completed":
                self._record(
                    capability=capability,
                    params=params,
                    allowed=True,
                    reason="Idempotent replay — cached result returned",
                    result=claim.result,
                    status=STATUS_ALLOWED,
                    action_type=resolved_type,
                    idempotency_key=idem_key,
                )
                return claim.result
            if claim.status == "in_progress":
                row = self._store.wait_for_idempotency(idem_key)
                if row is None or row["status"] not in ("completed", "failed"):
                    raise KyndConcurrentExecutionError(
                        f"idempotency_key {idem_key!r} is still being processed by "
                        f"another request and did not complete within the wait timeout"
                    )
                if row["status"] == "completed":
                    result = json.loads(row["result_json"]) if row["result_json"] is not None else None
                    self._record(
                        capability=capability,
                        params=params,
                        allowed=True,
                        reason="Idempotent replay — cached result returned",
                        result=result,
                        status=STATUS_ALLOWED,
                        action_type=resolved_type,
                        idempotency_key=idem_key,
                    )
                    return result
                # The concurrent owner's attempt failed. Fall through: this
                # caller becomes the new owner via claim_idempotency's
                # reclaim-on-failed logic and gets a genuine retry.
                claim2 = self._store.claim_idempotency(idem_key, capability)
                if claim2.status != "new":
                    raise KyndConcurrentExecutionError(
                        f"idempotency_key {idem_key!r}: could not claim ownership after "
                        f"the prior attempt failed (status={claim2.status})"
                    )
            # status == "new": this caller owns the key now; proceed to execute.
            return _NOT_RESOLVED

        cached = self._idempotency.get(idem_key)
        if cached is not None:
            cached_capability, cached_result = cached
            if cached_capability != capability:
                raise KyndExecutionError(
                    f"idempotency_key {idem_key!r} was already used for capability "
                    f"'{cached_capability}'; refusing to reuse it for '{capability}'"
                )
            self._record(
                capability=capability,
                params=params,
                allowed=True,
                reason="Idempotent replay — cached result returned",
                result=cached_result,
                status=STATUS_ALLOWED,
                action_type=resolved_type,
                idempotency_key=idem_key,
            )
            return cached_result
        return _NOT_RESOLVED

    def _finish_idempotency_success(self, idem_key: str | None, capability: str, result: Any) -> None:
        if idem_key is None:
            return
        if self._store is not None:
            self._store.complete_idempotency(idem_key, result)
        else:
            self._idempotency[idem_key] = (capability, result)

    def _finish_idempotency_failure(self, idem_key: str | None, error: str) -> None:
        if idem_key is None:
            return
        if self._store is not None:
            self._store.fail_idempotency(idem_key, error)
        # In-memory mode never cached failures either (unchanged behavior) —
        # nothing to undo there.

    # -- recording ----------------------------------------------------------

    def _deny_and_record(
        self,
        capability: str,
        params: dict[str, Any],
        reason: str,
        resolved_type: str,
        idem_key: str | None,
    ) -> None:
        self._record(
            capability=capability,
            params=params,
            allowed=False,
            reason=reason,
            result=None,
            status=STATUS_DENIED,
            action_type=resolved_type,
            idempotency_key=idem_key,
        )
        logger.warning("Denied capability=%s action_type=%s: %s", capability, resolved_type, reason)

    def _record(
        self,
        capability: str,
        params: dict[str, Any],
        allowed: bool,
        reason: str,
        result: Any,
        status: str,
        action_type: str | None = None,
        error: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Record an execution attempt."""
        self._execution_log.append(
            ExecutionRecord(
                timestamp=time.time(),
                capability=capability,
                params=params,
                allowed=allowed,
                reason=reason,
                result=result,
                status=status,
                action_type=action_type,
                error=error,
                idempotency_key=idempotency_key,
            )
        )
        if self._store is not None:
            self._store.append_execution(
                capability=capability,
                action_type=action_type,
                params=params,
                allowed=allowed,
                status=status,
                reason=reason,
                result=result,
                error=error,
                idempotency_key=idempotency_key,
            )

    @property
    def execution_log(self) -> list[ExecutionRecord]:
        """Get the local execution log view (most recent entries, up to the limit).

        Always populated. With a store configured, the durable copy also
        exists in SQLite and survives restarts — see ``store.recent_execution()``.
        """
        return list(self._execution_log)

    @property
    def audit_log(self) -> list[Any]:
        """Get the broker's local audit log view."""
        return self._broker.audit_log

    def calls_today(self, capability: str) -> int:
        """Calls made against a capability on the current UTC date."""
        return self._broker.calls_today(capability)

    def reset_daily_counts(self) -> None:
        """Operator override to clear call counts. Counts roll over by UTC date."""
        self._broker.reset_daily_counts()


class _NotResolved:
    """Sentinel: distinguishes 'no cached result' from a cached result of None."""

    def __repr__(self) -> str:
        return "<NOT_RESOLVED>"


_NOT_RESOLVED = _NotResolved()
