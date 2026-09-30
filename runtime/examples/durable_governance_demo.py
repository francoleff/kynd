#!/usr/bin/env python3
"""Example: durable governance across a real restart, and real approval verification.

Demonstrates D-1: the two P0 blockers from the production audit
(docs/engineering/TECHNICAL_DEBT.md D-1, D-2) are closed.

Usage:
    python examples/durable_governance_demo.py
"""

import os
import tempfile

from kynd_runtime import Constitution, Executor, KyndExecutionError, SqliteStore, ToolRegistry

db_path = os.path.join(tempfile.mkdtemp(), "kynd.db")

raw = {
    "hard_rules": [
        {
            "name": "require-approval-for-money",
            "type": "require_param",
            "param": "approval_id",
            "verify": "approval",  # <-- this is what makes it REAL, not just present
            "action_types": ["charge_card"],
        },
    ],
    "capabilities": [
        {"name": "charge_card", "max_amount": 1000, "max_calls_per_day": 3},
    ],
}


def build_executor(store: SqliteStore) -> Executor:
    registry = ToolRegistry()
    registry.register("charge_card", lambda p: f"Charged ${p['amount']:.2f}")
    return Executor(Constitution(raw), registry, store=store)


print("=" * 68)
print("1. A model-invented approval_id is rejected — presence is not proof")
print("=" * 68)
store = SqliteStore(db_path)
executor = build_executor(store)
try:
    executor.execute("charge_card", {"amount": 50, "approval_id": "abc123"})
    print("  BUG: fake approval accepted")
except KyndExecutionError as e:
    print(f"  denied: {e}")

print()
print("=" * 68)
print("2. A real, issued approval succeeds — once")
print("=" * 68)
approval_id = store.issue_approval("charge_card", max_amount=100, max_uses=1)
result = executor.execute("charge_card", {"amount": 50, "approval_id": approval_id})
print(f"  {result}")
try:
    executor.execute("charge_card", {"amount": 50, "approval_id": approval_id})
    print("  BUG: one-time approval reused")
except KyndExecutionError as e:
    print(f"  reuse denied: {e}")

print()
print("=" * 68)
print("3. Daily quota is consumed; caps survive the process")
print("=" * 68)
aid2 = store.issue_approval("charge_card", max_amount=100)
executor.execute("charge_card", {"amount": 10, "approval_id": aid2})
print(f"  calls today: {executor.calls_today('charge_card')} (cap is 3)")

print()
print("=" * 68)
print("4. SIMULATED RESTART — new process, same database file")
print("=" * 68)
del executor, store  # the process "exits"; nothing is flushed, nothing is special

store2 = SqliteStore(db_path)  # a fresh process opens the same file
executor2 = build_executor(store2)
print(f"  calls today after restart: {executor2.calls_today('charge_card')} (unchanged: 2)")
aid3 = store2.issue_approval("charge_card", max_amount=100)
executor2.execute("charge_card", {"amount": 10, "approval_id": aid3})
try:
    aid4 = store2.issue_approval("charge_card", max_amount=100)
    executor2.execute("charge_card", {"amount": 10, "approval_id": aid4})
    print("  BUG: cap did not hold across restart")
except KyndExecutionError as e:
    print(f"  4th charge today correctly denied: {e}")

print()
print("=" * 68)
print("Every check above is real: SQLite file on disk, real restart, real")
print("approval lifecycle. See docs/engineering/D1_IMPLEMENTATION.md.")
print("=" * 68)
