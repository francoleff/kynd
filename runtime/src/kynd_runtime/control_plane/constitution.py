"""Constitution loader — reads and validates the agent's constitution file.

The constitution is code, not a prompt. It is validated strictly at load time
so that a malformed or misspelled rule fails loudly at startup rather than
silently permitting an action during enforcement.
"""

from __future__ import annotations

import numbers
from pathlib import Path
from typing import Any

import yaml


class ConstitutionError(Exception):
    """Raised when the constitution file is invalid or missing."""


def _get_str(raw: dict[str, Any], key: str, default: str) -> str:
    """Typed accessor: reads ``key`` from a raw (untyped) dict as ``str``.

    ``_validate`` (below) already runtime-checks these fields at construction
    time, so this is not a new validation gate — it is what tells mypy what
    that runtime check already guarantees. A blind ``cast()`` here would
    assert the same thing without ever actually checking it; this does check,
    at negligible cost, so a future caller who somehow builds a Constitution
    from an unvalidated dict still fails safely instead of returning garbage
    silently typed as ``str``.
    """
    value = raw.get(key, default)
    return value if isinstance(value, str) else default


def _get_list_of_dict(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Typed accessor: reads ``key`` as a list of dicts, or ``[]``."""
    value = raw.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _get_dict_of_float(raw: dict[str, Any], key: str) -> dict[str, float]:
    """Typed accessor: reads ``key`` as a ``dict[str, float]``, or ``{}``."""
    value = raw.get(key, {})
    if not isinstance(value, dict):
        return {}
    return {
        k: float(v)
        for k, v in value.items()
        if isinstance(k, str) and isinstance(v, (int, float)) and not isinstance(v, bool)
    }


# Rule types the governance gate knows how to enforce. A rule with any other
# type would be silently skipped at check time, which would mean "allow" — so
# unknown types are rejected here, at load, instead.
KNOWN_RULE_TYPES = frozenset(
    {
        "block_action_type",
        "block_capability",
        "require_param",
        "block_param_value",
    }
)

# Required list-valued key per rule type. A rule of this type with an empty or
# missing list can never match anything, which is a silently inert safety rule.
_RULE_REQUIRED_LIST = {
    "block_action_type": "action_types",
    "block_capability": "capabilities",
    "block_param_value": "blocked_values",
}


class Constitution:
    """Parsed constitution with typed access to rules.

    Construct via :meth:`load` for file input, or directly with an already
    validated mapping. Both paths validate; there is no way to build an
    unvalidated Constitution.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        if not isinstance(raw, dict):
            raise ConstitutionError("Constitution must be a mapping at the top level")
        _validate(raw)
        self._raw = raw

    @classmethod
    def load(cls, path: str | Path) -> "Constitution":
        """Load a constitution from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise ConstitutionError(f"Constitution file not found: {path}")
        try:
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConstitutionError(f"Invalid YAML in constitution file: {e}") from e
        except OSError as e:
            raise ConstitutionError(f"Cannot read constitution file {path}: {e}") from e
        if not isinstance(raw, dict):
            raise ConstitutionError("Constitution must be a YAML mapping at the top level")
        try:
            return cls(raw)
        except ConstitutionError as e:
            raise ConstitutionError(f"{path}: {e}") from e

    @property
    def name(self) -> str:
        return _get_str(self._raw, "name", "unnamed")

    @property
    def mission(self) -> str:
        return _get_str(self._raw, "mission", "")

    @property
    def hard_rules(self) -> list[dict[str, Any]]:
        """Hard rules the brain cannot override."""
        return _get_list_of_dict(self._raw, "hard_rules")

    @property
    def money_caps(self) -> dict[str, float]:
        """Spend caps per capability (USD).

        Enforced by the governance gate alongside ``capability.max_amount``;
        whichever is stricter wins.
        """
        return _get_dict_of_float(self._raw, "money_caps")

    @property
    def capabilities(self) -> list[dict[str, Any]]:
        """Registered capabilities with their caps."""
        return _get_list_of_dict(self._raw, "capabilities")

    def get_capability(self, name: str) -> dict[str, Any] | None:
        """Get a capability config by name."""
        for cap in self.capabilities:
            if cap.get("name") == name:
                return cap
        return None

    def get_money_cap(self, capability_name: str) -> float | None:
        """Get the money cap for a specific capability."""
        return self.money_caps.get(capability_name)

    def effective_max_amount(self, capability_name: str) -> float | None:
        """Strictest spend ceiling for a capability, or None if uncapped.

        Considers both ``money_caps[name]`` and ``capability.max_amount``.
        """
        limits = []
        cap_config = self.get_capability(capability_name)
        if cap_config is not None and cap_config.get("max_amount") is not None:
            limits.append(float(cap_config["max_amount"]))
        money_cap = self.money_caps.get(capability_name)
        if money_cap is not None:
            limits.append(float(money_cap))
        return min(limits) if limits else None


def _err(where: str, message: str) -> ConstitutionError:
    return ConstitutionError(f"{where}: {message}")


def _validate(raw: dict[str, Any]) -> None:
    """Validate constitution structure. Raises ConstitutionError on any problem.

    Strict by design: a constitution that cannot be fully understood must not
    be used to make allow/deny decisions.
    """
    _validate_scalar(raw, "name", str)
    _validate_scalar(raw, "mission", str)
    _validate_hard_rules(raw.get("hard_rules"))
    _validate_capabilities(raw.get("capabilities"))
    _validate_money_caps(raw.get("money_caps"))


def _validate_scalar(raw: dict[str, Any], key: str, expected: type) -> None:
    value = raw.get(key)
    if value is not None and not isinstance(value, expected):
        raise _err(key, f"must be a {expected.__name__}, got {type(value).__name__}")


def _validate_hard_rules(rules: Any) -> None:
    if rules is None:
        return
    if not isinstance(rules, list):
        raise _err("hard_rules", f"must be a list, got {type(rules).__name__}")

    for index, rule in enumerate(rules):
        where = f"hard_rules[{index}]"
        if not isinstance(rule, dict):
            raise _err(where, f"must be a mapping, got {type(rule).__name__}")

        rule_type = rule.get("type")
        if not rule_type:
            raise _err(where, "missing required key 'type'")
        if rule_type not in KNOWN_RULE_TYPES:
            known = ", ".join(sorted(KNOWN_RULE_TYPES))
            raise _err(
                where,
                f"unknown rule type {rule_type!r}. A rule the gate cannot enforce "
                f"would silently permit everything. Known types: {known}",
            )

        required_list = _RULE_REQUIRED_LIST.get(rule_type)
        if required_list is not None:
            values = rule.get(required_list)
            if not isinstance(values, list) or not values:
                raise _err(
                    where,
                    f"rule type {rule_type!r} requires a non-empty list "
                    f"'{required_list}'; without it the rule can never match",
                )

        if rule_type in ("require_param", "block_param_value"):
            param = rule.get("param")
            if not isinstance(param, str) or not param:
                raise _err(where, f"rule type {rule_type!r} requires a non-empty string 'param'")

        scope = rule.get("action_types")
        if rule_type == "require_param" and scope is not None:
            if not isinstance(scope, list) or not scope:
                raise _err(where, "'action_types' scope must be a non-empty list when present")


def _validate_capabilities(caps: Any) -> None:
    if caps is None:
        return
    if not isinstance(caps, list):
        raise _err("capabilities", f"must be a list, got {type(caps).__name__}")

    seen: set[str] = set()
    for index, cap in enumerate(caps):
        where = f"capabilities[{index}]"
        if not isinstance(cap, dict):
            raise _err(where, f"must be a mapping, got {type(cap).__name__}")

        name = cap.get("name")
        if not isinstance(name, str) or not name:
            raise _err(where, "missing required non-empty string key 'name'")
        if name in seen:
            raise _err(
                where,
                f"duplicate capability {name!r}; the first definition would silently win",
            )
        seen.add(name)

        _validate_limit(f"{where}.max_amount", cap.get("max_amount"))
        _validate_limit(f"{where}.max_calls_per_day", cap.get("max_calls_per_day"))

        targets = cap.get("allowed_targets")
        if targets is not None:
            if not isinstance(targets, list):
                raise _err(f"{where}.allowed_targets", "must be a list")
            for target in targets:
                if not isinstance(target, str):
                    raise _err(
                        f"{where}.allowed_targets",
                        f"entries must be strings, got {type(target).__name__}",
                    )


def _validate_money_caps(caps: Any) -> None:
    if caps is None:
        return
    if not isinstance(caps, dict):
        raise _err("money_caps", f"must be a mapping, got {type(caps).__name__}")
    for name, value in caps.items():
        if not isinstance(name, str):
            raise _err("money_caps", f"keys must be strings, got {type(name).__name__}")
        _validate_limit(f"money_caps.{name}", value, required=True)


def _validate_limit(where: str, value: Any, required: bool = False) -> None:
    """A limit must be a non-negative real number. Booleans are not numbers here."""
    if value is None:
        if required:
            raise _err(where, "must not be null")
        return
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise _err(where, f"must be a number, got {type(value).__name__}")
    if value < 0:
        raise _err(where, f"must not be negative, got {value}")
