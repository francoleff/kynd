"""Compile a workspace's stored governance configuration into a real
`kynd_runtime.Constitution`.

This module is the seam between the SaaS and the enforcement core. Two rules
govern everything in it:

1. It emits ONLY the four rule types the runtime can actually enforce. The
   runtime's `KNOWN_RULE_TYPES` is imported rather than re-declared, so if the
   runtime's vocabulary ever changes, this file fails loudly instead of
   silently emitting a rule the gate will refuse.

2. It creates no governance semantics of its own. There is no second rule
   engine here — this is a translation from database rows to the dict shape
   the runtime already validates. The runtime remains the source of truth for
   what a rule MEANS.

Mission section 13: "Do NOT create a second governance language."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kynd_runtime import Constitution, ConstitutionError
from kynd_runtime.control_plane.constitution import KNOWN_RULE_TYPES

from ..models import GovernanceRule, Workspace, WorkspaceCapability

# The name of the param that carries a human approval into the runtime. Fixed,
# not customer-configurable: it is an internal protocol detail between the
# approval service and the runtime, and letting a customer rename it would let
# them rename it to something the approval service never populates.
APPROVAL_PARAM = "approval_id"


class GovernanceConfigError(Exception):
    """A workspace's governance configuration cannot be compiled.

    Raised at SAVE time so a customer sees a readable error while editing,
    rather than at execution time when the action they care about is blocked
    by a config problem they cannot see.
    """


@dataclass
class CompiledConstitution:
    """A validated constitution plus what it was built from."""

    constitution: Constitution
    raw: dict[str, Any]
    capability_names: list[str] = field(default_factory=list)
    approval_required: list[str] = field(default_factory=list)

    def describe(self) -> dict[str, Any]:
        """A UI-safe summary: what Kynd can do, cannot do, and must ask about.

        Rendered by the Governance page. Deliberately built from the COMPILED
        constitution rather than from the database rows, so the dashboard shows
        what is actually enforced, not what someone intended to configure.
        """
        blocked_capabilities: list[str] = []
        blocked_action_types: list[str] = []
        for rule in self.constitution.hard_rules:
            if rule.get("type") == "block_capability":
                blocked_capabilities.extend(rule.get("capabilities", []))
            elif rule.get("type") == "block_action_type":
                blocked_action_types.extend(rule.get("action_types", []))

        return {
            "allowed": [
                name for name in self.capability_names if name not in blocked_capabilities
            ],
            "blocked_capabilities": blocked_capabilities,
            "blocked_action_types": blocked_action_types,
            "approval_required": list(self.approval_required),
            "limits": {
                name: {
                    "max_amount": self.constitution.effective_max_amount(name),
                    "max_calls_per_day": (
                        self.constitution.get_capability(name) or {}
                    ).get("max_calls_per_day"),
                    "allowed_targets": (
                        self.constitution.get_capability(name) or {}
                    ).get("allowed_targets"),
                }
                for name in self.capability_names
            },
        }


def _validate_rule_shape(rule: GovernanceRule) -> dict[str, Any]:
    """Turn one stored rule into the dict the runtime expects.

    Every branch validates the payload the runtime requires for that rule type.
    The runtime would reject a malformed rule anyway — this exists so the
    rejection carries a message about the customer's own rule name rather than
    an index into a generated list.
    """
    rule_type = rule.rule_type
    config = rule.config or {}

    if rule_type not in KNOWN_RULE_TYPES:
        raise GovernanceConfigError(
            f"Rule '{rule.name}' has type '{rule_type}', which Kynd cannot enforce. "
            f"Supported types: {', '.join(sorted(KNOWN_RULE_TYPES))}."
        )

    compiled: dict[str, Any] = {"name": rule.name, "type": rule_type}

    if rule_type == "block_action_type":
        values = config.get("action_types")
        if not isinstance(values, list) or not values:
            raise GovernanceConfigError(
                f"Rule '{rule.name}' blocks action types but lists none, so it "
                f"would never block anything."
            )
        compiled["action_types"] = [str(v) for v in values]

    elif rule_type == "block_capability":
        values = config.get("capabilities")
        if not isinstance(values, list) or not values:
            raise GovernanceConfigError(
                f"Rule '{rule.name}' blocks capabilities but lists none, so it "
                f"would never block anything."
            )
        compiled["capabilities"] = [str(v) for v in values]

    elif rule_type == "require_param":
        param = config.get("param")
        if not isinstance(param, str) or not param:
            raise GovernanceConfigError(
                f"Rule '{rule.name}' requires a parameter but does not say which."
            )
        compiled["param"] = param
        if config.get("verify") == "approval":
            compiled["verify"] = "approval"
        scope = config.get("action_types")
        if scope is not None:
            if not isinstance(scope, list) or not scope:
                raise GovernanceConfigError(
                    f"Rule '{rule.name}' has an empty scope; remove the scope to "
                    f"apply it everywhere, or name at least one action type."
                )
            compiled["action_types"] = [str(v) for v in scope]

    elif rule_type == "block_param_value":
        param = config.get("param")
        values = config.get("blocked_values")
        if not isinstance(param, str) or not param:
            raise GovernanceConfigError(
                f"Rule '{rule.name}' blocks a parameter value but does not say "
                f"which parameter."
            )
        if not isinstance(values, list) or not values:
            raise GovernanceConfigError(
                f"Rule '{rule.name}' blocks values but lists none, so it would "
                f"never block anything."
            )
        compiled["param"] = param
        compiled["blocked_values"] = values

    return compiled


def compile_constitution(
    workspace: Workspace,
    capabilities: list[WorkspaceCapability],
    rules: list[GovernanceRule],
) -> CompiledConstitution:
    """Build a runtime Constitution from a workspace's configuration.

    Raises GovernanceConfigError with a customer-readable message if the
    configuration cannot produce a valid constitution.
    """
    enabled_capabilities = [cap for cap in capabilities if cap.enabled]

    compiled_capabilities: list[dict[str, Any]] = []
    approval_required: list[str] = []

    for cap in enabled_capabilities:
        entry: dict[str, Any] = {"name": cap.name}

        if cap.max_amount is not None:
            if cap.max_amount < 0:
                raise GovernanceConfigError(
                    f"Capability '{cap.name}' has a negative maximum amount."
                )
            entry["max_amount"] = float(cap.max_amount)

        if cap.max_calls_per_day is not None:
            if cap.max_calls_per_day < 0:
                raise GovernanceConfigError(
                    f"Capability '{cap.name}' has a negative daily call limit."
                )
            entry["max_calls_per_day"] = int(cap.max_calls_per_day)

        # None => no allowlist. [] => an allowlist permitting nothing. These are
        # different statements and the runtime treats them differently, so the
        # distinction is preserved rather than normalised away.
        if cap.allowed_targets is not None:
            if not isinstance(cap.allowed_targets, list):
                raise GovernanceConfigError(
                    f"Capability '{cap.name}' has a malformed target allowlist."
                )
            entry["allowed_targets"] = [str(t) for t in cap.allowed_targets]

        compiled_capabilities.append(entry)

        if cap.requires_approval:
            approval_required.append(cap.name)

    compiled_rules = [_validate_rule_shape(rule) for rule in rules if rule.enabled]

    # Capabilities marked "requires approval" become ONE scoped hard rule each.
    # Scoping by capability name (rather than one global rule) means enabling
    # approval for `send_email` cannot accidentally start demanding approval
    # for every other capability in the workspace.
    for name in approval_required:
        compiled_rules.append(
            {
                "name": f"approval-required-{name}",
                "type": "require_param",
                "param": APPROVAL_PARAM,
                "verify": "approval",
                "action_types": [name],
            }
        )

    raw: dict[str, Any] = {
        "name": workspace.slug,
        "mission": f"Governance for {workspace.name}",
        "capabilities": compiled_capabilities,
        "hard_rules": compiled_rules,
    }

    try:
        constitution = Constitution(raw)
    except ConstitutionError as exc:
        # The runtime's own validator rejected it. Surface its message — it is
        # specific and accurate — rather than inventing a vaguer one.
        raise GovernanceConfigError(str(exc)) from exc

    return CompiledConstitution(
        constitution=constitution,
        raw=raw,
        capability_names=[cap["name"] for cap in compiled_capabilities],
        approval_required=approval_required,
    )
