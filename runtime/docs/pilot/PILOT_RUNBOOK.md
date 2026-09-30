# PILOT RUNBOOK — Kynd Runtime

## Level progression (advance only on evidence, per mission Phase 9)

### LEVEL 0 — Read-only / dry-run (minimum 3-5 real trigger events)

The AI/script proposes a `send_notification` action. The pilot operator
runs it through `GovernanceGate.check()` directly (NOT `Executor.execute()`)
so **no real send handler is ever invoked** — this evaluates whether the
proposal would be allowed, with zero side effects:

```python
from kynd_runtime.control_plane.governance_gate import Action

action = Action(type="send", capability="send_notification",
                 params={"target": "...", "approval_id": "..."})
result = gate.check(action)
print(result.allowed, result.reason)
```

**Exit Level 0 when:** the proposals the AI/script generates are
consistently the shape you expect (correct capability name, correct target,
sensible content) across at least 3-5 real trigger events, with zero
surprises in what would have been allowed/denied.

### LEVEL 1 — AI proposes, human approves, real send (recommended: 1-2 weeks)

Real sends happen, but **every single one requires a human to call**
`store.issue_approval("send_notification", max_uses=1, ttl_seconds=3600)`
before the AI's proposed action is submitted to `Executor.execute()`. No
approval, no send — verified directly (see PILOT_SAFETY.md's failure
categories: a missing or forged `approval_id` is denied every time).

The approver is a real named person (see PILOT_SETUP.md item 2), not an
automated step. This is the actual human-in-the-loop the mission requires,
enforced by code, not by policy: `Executor.execute()` raises
`KyndExecutionError` if the approval is missing, forged, expired, or already
consumed.

**Exit Level 1 when:** the daily cap has never been hit unexpectedly, zero
unapproved sends were attempted (or all attempts were correctly blocked),
and the approver reports low friction (each approval takes under a minute).

### LEVEL 2 — Low-risk automated approval (only after Level 1 evidence)

Not part of this pilot's initial scope. If Level 1 shows the AI's proposals
are reliable and the human approval step is pure friction with no real
decision being made, the customer may choose to pre-authorize approvals
(e.g., issue a `max_uses=5, ttl_seconds=86400` daily-batch approval each
morning) rather than approving one-by-one. This requires an explicit
customer decision after Level 1 evidence exists — not before.

### LEVEL 3 — Broader automation

Out of scope for this pilot entirely. Would require a new capability
declaration, a new constitution review, and a new pilot scope document. Do
not progress here based on calendar time or enthusiasm.

## Operator quick-reference during the pilot

**Issue an approval (Level 1):**
```python
approval_id = store.issue_approval("send_notification", max_uses=1, ttl_seconds=3600)
# hand this approval_id to whatever process submits the proposed action
```

**Check today's send count:**
```python
from datetime import date
store.calls_today(date.today().isoformat(), "send_notification")
```

**Read the audit trail:**
```python
for row in store.recent_execution():
    print(row["status"], row["capability"], row["reason"], row["params"])
```

**Answer "was this specific approval used?":**
```python
row = store.get_approval(approval_id)
print(row["use_count"], row["last_consumed_at"])
```

See PILOT_KILL_SWITCH section in PILOT_SAFETY.md-adjacent operations below
(also duplicated in PILOT_INCIDENT_RESPONSE.md) for how to stop everything
immediately.
