"""Governance gate — validates every action the brain proposes against the constitution.

Fail-closed: anything the gate cannot positively confirm as permitted is a
violation. That includes rule types it does not recognise, amounts it cannot
interpret as money, and approvals it cannot verify.
"""

from __future__ import annotations

import numbers
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Protocol

from .constitution import KNOWN_RULE_TYPES, Constitution
from ..domain_types import ActionType, CapabilityName

if TYPE_CHECKING:
    # Import-only-for-typing: keeps the runtime import graph exactly as
    # before (GovernanceGate never imports persistence at runtime — an
    # ApprovalStore is anything structurally matching the Protocol below,
    # which is the whole point of using a Protocol here) while still giving
    # mypy the real return type instead of `Any`.
    from ..persistence import ApprovalCheck


class ApprovalStore(Protocol):
    """The subset of SqliteStore's approval API the gate needs.

    A Protocol, not a concrete import, so the gate stays decoupled from the
    persistence module's implementation — anything with this shape works.
    """

    def validate_approval(
        self,
        approval_id: str,
        capability: str,
        action_type: str | None = None,
        amount: float | None = None,
        target: str | None = None,
    ) -> "ApprovalCheck": ...


@dataclass
class Action:
    """An action proposed by the brain.

    ``type`` is the *semantic* kind of the action (``delete``, ``charge``,
    ``send``). ``capability`` is the registered handler name
    (``delete_all_customers``, ``charge_card``). They are deliberately distinct:
    rules that block a kind of action must match capabilities whose names do
    not happen to equal that kind.
    """

    type: ActionType
    capability: CapabilityName
    params: dict[str, Any] = field(default_factory=dict)
    amount: float | None = None  # For money-moving actions

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(
            type=ActionType(data.get("type", "unknown")),
            capability=CapabilityName(data.get("capability", "unknown")),
            params=data.get("params", {}),
            amount=data.get("amount"),
        )


@dataclass
class GateResult:
    """Result of a governance gate check."""

    allowed: bool
    reason: str
    action: Optional[Action] = None
    violations: list[str] = field(default_factory=list)


class GovernanceGate:
    """
    Every action the brain proposes is checked by code before it happens.
    The brain can propose anything; it can never execute anything.

    ``approval_store``, if supplied, enables ``verify: approval`` on
    ``require_param`` rules — see the ``require_param`` branch below for what
    that actually checks. Without a store, a rule that asks for approval
    verification denies outright rather than silently trusting that the
    param's mere presence means a human approved it.
    """

    def __init__(
        self, constitution: Constitution, approval_store: "ApprovalStore | None" = None
    ) -> None:
        self._constitution = constitution
        self._approval_store = approval_store

    def check(self, action: Action) -> GateResult:
        """Check an action against the constitution. Returns GateResult.

        Read-only: verifies an approval would currently be accepted but does
        NOT consume it. Consumption is an atomic claim performed by the
        executor only after every other check (gate + broker) has also
        passed — see ``Executor.execute``. Two concurrent requests can both
        pass this read-only check for a one-time approval; only one of them
        will win the atomic consume.
        """
        violations: list[str] = []

        # 1. Check hard rules
        for rule in self._constitution.hard_rules:
            violation = self._check_hard_rule(action, rule)
            if violation:
                violations.append(violation)

        # 2. Check capability exists
        cap_config = self._constitution.get_capability(action.capability)
        if cap_config is None:
            violations.append(f"Unknown capability: {action.capability}")

        # 3. Check money cap
        if action.amount is not None:
            violation = self._check_money_cap(action)
            if violation:
                violations.append(violation)

        if violations:
            return GateResult(
                allowed=False,
                reason=f"Blocked by governance gate: {'; '.join(violations)}",
                action=action,
                violations=violations,
            )

        return GateResult(
            allowed=True,
            reason="Action permitted by governance gate",
            action=action,
        )

    def approvals_to_consume(self, action: Action) -> list[tuple[str, str, str]]:
        """Approvals this action must atomically consume if it proceeds.

        Returns a list of ``(rule_name, param_name, approval_id)``. The
        executor calls this after gate + broker both pass, and consumes each
        one via the approval store before invoking the tool handler. Kept
        separate from ``check()`` because ``check()`` must stay side-effect
        free — a caller can evaluate the gate speculatively (e.g. to preview
        whether an action would be permitted) without consuming anything.
        """
        out: list[tuple[str, str, str]] = []
        for rule in self._constitution.hard_rules:
            if rule.get("type") != "require_param" or rule.get("verify") != "approval":
                continue
            applies_to = rule.get("action_types")
            if applies_to is not None and not self._in_scope(action, applies_to):
                continue
            param = rule.get("param")
            if not param:
                continue
            value = action.params.get(param)
            if isinstance(value, str) and value:
                out.append((rule.get("name", "<unnamed>"), param, value))
        return out

    def _check_hard_rule(self, action: Action, rule: dict[str, Any]) -> str | None:
        """Check a single hard rule against an action. Returns violation message or None."""
        rule_type = rule.get("type")
        name = rule.get("name", "<unnamed>")

        # Fail closed. Constitution.load rejects unknown rule types, but a
        # Constitution can also be built from a dict at runtime, and a rule the
        # gate cannot enforce must never read as "permitted".
        if rule_type not in KNOWN_RULE_TYPES:
            return (
                f"Hard rule '{name}': unenforceable rule type {rule_type!r} "
                f"— denying because the gate cannot evaluate it"
            )

        if rule_type == "block_action_type":
            blocked = rule.get("action_types", [])
            # Match on the action's semantic type OR its capability name. The
            # capability check is what makes `block_action_type: [delete]` stop
            # a capability called `delete_all_customers`.
            if action.type in blocked:
                return f"Hard rule '{name}': action type '{action.type}' is blocked"
            matched = _match_capability_to_action_types(action.capability, blocked)
            if matched is not None:
                return (
                    f"Hard rule '{name}': capability '{action.capability}' "
                    f"performs blocked action type '{matched}'"
                )

        elif rule_type == "block_capability":
            if action.capability in rule.get("capabilities", []):
                return f"Hard rule '{name}': capability '{action.capability}' is blocked"

        elif rule_type == "require_param":
            # Optional scoping: rule applies only to these action types.
            applies_to = rule.get("action_types")
            if applies_to is not None and not self._in_scope(action, applies_to):
                return None
            required_param = rule.get("param")
            if required_param and required_param not in action.params:
                return f"Hard rule '{name}': missing required param '{required_param}'"

            # A present param is not automatically a valid approval. Presence
            # alone is what the un-hardened version trusted — this is D-2's fix.
            if required_param and rule.get("verify") == "approval":
                approval_id = action.params.get(required_param)
                if not isinstance(approval_id, str) or not approval_id.strip():
                    return (
                        f"Hard rule '{name}': '{required_param}' must be a "
                        f"non-empty string approval id"
                    )
                if self._approval_store is None:
                    # Fail closed. A model-generated string must never pass
                    # "approval verification" just because nothing is there
                    # to check it against.
                    return (
                        f"Hard rule '{name}': approval verification is required "
                        f"but no approval store is configured — a present "
                        f"'{required_param}' is not treated as a real approval"
                    )
                target = action.params.get("target")
                result = self._approval_store.validate_approval(
                    approval_id,
                    capability=action.capability,
                    action_type=action.type,
                    amount=action.amount,
                    target=target,
                )
                if not result.ok:
                    return f"Hard rule '{name}': {result.reason}"

        elif rule_type == "block_param_value":
            param = rule.get("param")
            blocked_values = rule.get("blocked_values", [])
            if param in action.params and action.params[param] in blocked_values:
                return f"Hard rule '{name}': param '{param}' has blocked value"

        return None

    @staticmethod
    def _in_scope(action: Action, action_types: list[str]) -> bool:
        """Whether a scoped rule applies to this action.

        Scope matches the action type, the capability name, or a capability
        whose name contains a scoped action type as a word.
        """
        if action.type in action_types or action.capability in action_types:
            return True
        return _match_capability_to_action_types(action.capability, action_types) is not None

    def _check_money_cap(self, action: Action) -> str | None:
        """Check an action's amount against the strictest configured ceiling."""
        amount = action.amount

        # Untrusted input: a model may emit "600" or None or a bool. Anything
        # that is not a real, finite, non-negative number is a denial, not a
        # crash and not a pass.
        if isinstance(amount, bool) or not isinstance(amount, numbers.Real):
            return (
                f"Amount must be a number for capability '{action.capability}', "
                f"got {type(amount).__name__}: {amount!r}"
            )
        amount = float(amount)
        if amount != amount or amount in (float("inf"), float("-inf")):  # NaN / inf
            return f"Amount must be a finite number for capability '{action.capability}'"
        if amount < 0:
            return (
                f"Amount ${amount:.2f} is negative for capability "
                f"'{action.capability}'; negative amounts are not permitted"
            )

        cap_config = self._constitution.get_capability(action.capability)
        if cap_config is None:
            return f"No capability config for '{action.capability}', cannot verify money cap"

        max_amount = self._constitution.effective_max_amount(action.capability)
        if max_amount is not None and amount > max_amount:
            return (
                f"Amount ${amount:.2f} exceeds max ${max_amount:.2f} "
                f"for capability '{action.capability}'"
            )
        return None


def _match_capability_to_action_types(capability: str, action_types: list[Any]) -> str | None:
    """Return the blocked action type a capability name performs, if any.

    Capability names are conventionally ``<verb>_<object>`` — ``delete_users``,
    ``drop_table``, ``purge_cache``. A rule blocking the verb ``delete`` must
    stop ``delete_users``, otherwise the rule is decorative.

    Matching is on word boundaries (``_`` or ``-`` separated), so ``delete``
    matches ``delete_users`` and ``soft_delete`` but not ``undeletable``.
    """
    if not capability:
        return None
    words = {w for w in capability.replace("-", "_").lower().split("_") if w}
    for action_type in action_types:
        if not isinstance(action_type, str):
            continue
        if action_type.lower() in words:
            return action_type
    return None
