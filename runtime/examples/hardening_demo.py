#!/usr/bin/env python3
"""Example: the governance behaviours that a naive implementation gets wrong.

Each demo below corresponds to a finding in docs/engineering/ARCHITECTURE_AUDIT.md
that was CONFIRMED broken and then fixed. Run it to see the enforcement hold.

Usage:
    python examples/hardening_demo.py
"""

from pathlib import Path

from kynd_runtime import (
    Constitution,
    ConstitutionError,
    Executor,
    KyndExecutionError,
    ToolRegistry,
    Verifier,
)

EXAMPLES = Path(__file__).parent


def banner(finding: str, title: str) -> None:
    print()
    print("=" * 68)
    print(f"{finding} — {title}")
    print("=" * 68)


def build(raw: dict, capabilities: list[str]) -> tuple[Executor, list]:
    """Executor whose handlers shout when they actually fire."""
    fired: list[str] = []
    registry = ToolRegistry()
    for name in capabilities:
        def make(n):
            def handler(params):
                fired.append(n)
                return f"!! REAL SIDE EFFECT: {n} !!"
            return handler
        registry.register(name, make(name))
    return Executor(Constitution(raw), registry), fired


# --- F-1 ---------------------------------------------------------------------
banner("F-1", "A destructive capability is blocked by a verb rule")

executor, fired = build(
    {
        "hard_rules": [
            {
                "name": "no-destructive-actions",
                "type": "block_action_type",
                "action_types": ["delete", "destroy", "drop", "purge"],
            }
        ],
        "capabilities": [
            {"name": "delete_all_customers", "max_calls_per_day": 10},
            {"name": "send_email", "max_calls_per_day": 10},
        ],
    },
    ["delete_all_customers", "send_email"],
)

for capability in ("delete_all_customers", "send_email"):
    try:
        print(f"  {capability:<24} -> {executor.execute(capability, {'target': 'x'})}")
    except KyndExecutionError as e:
        print(f"  {capability:<24} -> BLOCKED: {e}")
print(f"  handlers that actually fired: {fired}")
print("  The rule says 'delete'. The capability is 'delete_all_customers'.")
print("  It is caught. Before hardening, it executed.")


# --- F-2 ---------------------------------------------------------------------
banner("F-2", "money_caps is enforced, and the strictest cap wins")

executor, fired = build(
    {
        "money_caps": {"charge_card": 50.0},
        "capabilities": [
            {"name": "charge_card", "max_amount": 500.0, "max_calls_per_day": 10}
        ],
    },
    ["charge_card"],
)
for amount in (25, 100):
    try:
        print(f"  charge ${amount:<6} -> {executor.execute('charge_card', {'amount': amount})}")
    except KyndExecutionError as e:
        print(f"  charge ${amount:<6} -> BLOCKED: {e}")
print("  max_amount is 500 but money_caps is 50. The stricter one applies.")


# --- F-3 ---------------------------------------------------------------------
banner("F-3", "A misspelled rule type is rejected, not ignored")

try:
    Constitution(
        {
            "hard_rules": [
                {"name": "oops", "type": "block_action_typo", "action_types": ["delete"]}
            ],
            "capabilities": [{"name": "delete_users"}],
        }
    )
    print("  loaded (BAD — this should not happen)")
except ConstitutionError as e:
    print(f"  ConstitutionError: {e}")
print("  A safety rule the gate cannot enforce must never mean 'allow'.")


# --- F-6 ---------------------------------------------------------------------
banner("F-6", "Untrusted model output cannot bypass or crash the money cap")

executor, fired = build(
    {"capabilities": [{"name": "charge_card", "max_amount": 500.0, "max_calls_per_day": 10}]},
    ["charge_card"],
)
for amount in ["600", -9999, float("nan"), True, 100]:
    try:
        result = executor.execute("charge_card", {"amount": amount})
        print(f"  amount={str(amount):<8} -> {result}")
    except KyndExecutionError as e:
        print(f"  amount={str(amount):<8} -> DENIED: {e}")
print(f"  handlers that actually fired: {len(fired)} (only the valid $100)")


# --- F-11 --------------------------------------------------------------------
banner("F-11", "A retried webhook does not charge twice")

executor, fired = build(
    {"capabilities": [{"name": "charge_card", "max_amount": 500.0, "max_calls_per_day": 10}]},
    ["charge_card"],
)
for attempt in range(1, 4):
    result = executor.execute("charge_card", {"amount": 100, "idempotency_key": "n8n-run-42"})
    print(f"  delivery {attempt} -> {result}")
print(f"  handler invocations: {len(fired)}   quota consumed: {executor.calls_today('charge_card')}")


# --- F-5 ---------------------------------------------------------------------
banner("F-5", "A failed side effect is not audited as a success")

registry = ToolRegistry()
registry.register("send_email", lambda p: (_ for _ in ()).throw(RuntimeError("smtp down")))
executor = Executor(
    Constitution({"capabilities": [{"name": "send_email", "max_calls_per_day": 10}]}), registry
)
try:
    executor.execute("send_email", {"target": "team@kynd.io"})
except RuntimeError as e:
    print(f"  handler raised: {e}")
record = executor.execution_log[-1]
print(f"  record.allowed = {record.allowed}   (governance permitted it)")
print(f"  record.status  = {record.status!r}   (but it did not happen)")
print(f"  record.error   = {record.error}")


# --- F-9 ---------------------------------------------------------------------
banner("F-9", "A verifier with no checks does not report success")

result = Verifier().verify({"task": "deploy"})
print(f"  passed = {result.passed}")
print(f"  failures = {result.failures}")
print("  'Nothing was checked' is not evidence that the work was done.")

print()
print("=" * 68)
print("All demonstrated behaviours are covered by tests/test_regressions_hardening.py")
print("=" * 68)
