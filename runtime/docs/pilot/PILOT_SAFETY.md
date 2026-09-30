# PILOT SAFETY — Kynd Runtime

## The safety boundary (verified, not assumed)

```
CUSTOMER INPUT / TRIGGER
        │
        ▼
AI / SCRIPT PROPOSES an action (capability + params)
        │                                    ← Kynd never sees this stage;
        │                                      it is pure proposal, no authority
        ▼
Executor.execute(capability, params, action_type=...)
        │
        ▼
RUNTIME VALIDATION (Executor + GovernanceGate)
  - params must be a dict
  - amount, if present, must be a real finite non-negative number
  - idempotency_key, if present, must be a string
        │
        ▼
CONSTITUTION (loaded once at startup, validated strictly — an
  unrecognised rule type is REJECTED AT LOAD, never silently skipped)
        │
        ▼
GOVERNANCE GATE
  - hard rules (block_action_type, block_capability, require_param,
    block_param_value) — fail closed on anything it cannot evaluate
  - unknown capability → denied
  - money cap (not used in this pilot: no money-moving capability exists)
        │
        ▼
APPROVAL (if the constitution requires it via verify: approval)
  - a present approval_id is NOT sufficient — it must be a real,
    unexpired, unconsumed, correctly-scoped token issued by
    SqliteStore.issue_approval(), which only the pilot's designated human
    approver can call
        │
        ▼
IDEMPOTENCY
  - a repeated idempotency_key returns the cached prior result; the real
    handler is never invoked twice for the same key
        │
        ▼
EXECUTION (the customer-provided handler — the ONLY place a real side
  effect happens)
        │
        ▼
AUDIT (durable, SQLite, survives restart — every attempt recorded,
  allowed/denied/failed, independent of whether the send succeeded)
```

**The AI never becomes the authority.** It can propose a capability, params,
and an approval_id — every one of those is independently checked against
durable, code-enforced state. A forged approval_id, a wrong capability name,
an over-cap amount, all fail at the GOVERNANCE GATE / APPROVAL stage before
any external call. This was re-verified in the customer readiness audit
immediately preceding this pilot prep (14 failure categories, all fail safe
— see the failure-audit evidence in the assistant's prior turn).

## Concrete pilot constitution (least privilege)

```yaml
name: pilot-notification-agent
mission: Send a single governed notification for the pilot customer. Nothing else.

hard_rules:
  - name: no-destructive-actions
    type: block_action_type
    action_types: [delete, destroy, drop, purge]

  - name: require-approval-for-send
    type: require_param
    param: approval_id
    verify: approval
    action_types: [send_notification]

capabilities:
  - name: send_notification
    max_calls_per_day: 5          # customer-adjustable; start low
    allowed_targets:
      - "REPLACE_WITH_CUSTOMER_APPROVED_ADDRESS"
```

Only ONE capability is declared. `charge_card`, `delete_*`, or any other
capability the library supports is simply absent from this file — Kynd
denies any capability name not present in the constitution
(`Unknown capability: X`), so there is no way for a proposed action naming a
different capability to execute, regardless of what the AI proposes.

## Capability classification (Phase 3 requirement)

| Capability | Class | Enabled this pilot? |
|---|---|---|
| `send_notification` | WRITE (one recipient, one channel) | **Yes** — the only one |
| Any `charge_*` / money-moving | WRITE, high-impact | No — not declared |
| Any `delete_*` / `drop_*` / `purge_*` | DESTRUCTIVE | No — blocked by hard rule AND not declared |
| Read-only queries (e.g. `get_status`) | READ | Not part of this pilot's scope; add only with evidence of need |

Default posture: nothing is enabled unless explicitly declared in the
constitution above. There is no "broad grant" mode in Kynd — every
capability must be named.

## What "safe" actually means here, precisely

- **Reversible in principle, not in fact.** A sent message cannot be
  unsent. Safety comes from volume cap (5/day), single-recipient
  allowlisting, and mandatory human approval — not from the ability to
  undo a send.
- **Fail-closed confirmed.** Every ambiguous or malformed input (bad
  amount, unknown capability, missing param, forged approval) is a denial,
  never a silent pass. Verified directly in this session's failure audit.
- **Exactly-once is NOT claimed.** If the pilot process crashes between
  "handler ran" and "result recorded," a retry with the same idempotency
  key may re-invoke the handler. This is a documented, inherent limit (see
  `docs/engineering/D1_IMPLEMENTATION.md` Crash Recovery Model) — mitigated
  here by low volume (a human approver is issuing at most 5 approvals/day,
  making a crash-during-send collision very unlikely to go unnoticed) and by
  choosing a notification (not a payment) as the pilot action, where a rare
  duplicate is an inconvenience, not a financial loss.
