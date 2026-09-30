# PILOT METRICS — Kynd Runtime

## What to measure (Phase 10 checklist, mapped to real queryable state)

All of these are answerable from `store.recent_execution()` and
`store.recent_audit()` without any additional instrumentation — Kynd
Runtime already records the fields needed. No new logging system required
for a pilot at this volume (max 5 sends/day).

| Metric | Source query |
|---|---|
| Actions proposed | count of rows in `store.recent_execution()` |
| Actions approved (Level 1) | count of `store.get_approval(id)["use_count"] > 0` per issued approval |
| Actions rejected (governance) | rows where `status == "denied"` |
| Actions executed | rows where `status == "allowed"` |
| Execution failures | rows where `status == "failed"` |
| Duplicate attempts (deduped) | rows where `idempotency_key` repeats across `recent_execution()` |
| Governance blocks | `status == "denied"`, `reason` starts with "Blocked by governance gate" |
| Approval failures | `status == "denied"`, `reason` contains "Hard rule" and an approval-related message (not found / expired / consumed / revoked) |
| External API failures | `status == "failed"`, `error` field populated (the handler raised) |
| Model failures | proposals that never reach `execute()` at all — must be tracked OUTSIDE Kynd, in whatever wraps the AI call; Kynd only sees what is proposed to it |
| Operator interventions | manual approvals issued (Level 1) — count of `issue_approval()` calls, tracked by the approver, since Kynd does not label *why* an approval was issued |
| Customer corrections | outside Kynd's visibility — must be tracked by the customer/operator manually (e.g. "I edited the draft before approving it 3 times this week") |

## Explicitly NOT auto-tracked by Kynd (operator must track manually)

- **Time saved.** Kynd has no concept of the "old way" this replaces. The
  operator must record a baseline (how long did this take before) and
  compare.
- **Customer satisfaction / trust.** Not a system metric — see
  PILOT feedback questions in the mission's Phase 12, asked directly.
- **False positives/negatives** in the sense of "the AI proposed something
  wrong but Kynd correctly allowed it because it matched the rules." Kynd
  can only tell you whether ITS decision matched the constitution, not
  whether the constitution itself was right. A false positive here means:
  the constitution allowed something the customer, after the fact, wishes
  it hadn't. Record these manually in PILOT_FAILURE_LOG.md.

## Minimal collection script (uses only documented public API)

```python
from datetime import date
from kynd_runtime import SqliteStore

store = SqliteStore("kynd_pilot.db")
rows = store.recent_execution()

by_status = {}
for r in rows:
    by_status[r["status"]] = by_status.get(r["status"], 0) + 1

print("Total proposals seen by Kynd:", len(rows))
print("By status:", by_status)
print("Sends today so far:", store.calls_today(date.today().isoformat(), "send_notification"))
```

This was written and is runnable as-is against a real pilot database — not
aspirational.
