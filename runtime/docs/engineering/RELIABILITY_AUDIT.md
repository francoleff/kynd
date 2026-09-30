# RELIABILITY AUDIT — Kynd Runtime

## The central reliability fact

**Kynd has no durable state.** Every counter, every audit entry, every
idempotency key lives in a Python process's memory. This single fact drives
almost every finding below and is the main reason the system is not yet
production ready.

---

## R-1 — Restart erases all governance state. P0. OPEN (partially mitigated).

`Broker._call_counts`, `Broker._audit_log`, `Executor._execution_log`, and
`Executor._idempotency` are all in-process.

Reproduced before the fix:

```
3rd call correctly blocked: exceeded max calls per day (2)
after 'restart': charge_card:EXECUTED
```

Consequences:

1. **Cap evasion by crash.** A worker that crashes and restarts gets a fresh
   quota every time. `max_calls_per_day: 10` on `charge_card` is unbounded if
   the process is unstable.
2. **Audit loss.** The audit trail dies with the process. An audit log that
   cannot survive a crash cannot answer "what did the agent do yesterday?" —
   which is the entire reason it exists.
3. **Idempotency loss.** Dedupe keys vanish on restart, so a retry that spans a
   restart re-executes.

**Mitigated this pass:** counters are now keyed by UTC date and roll over
correctly, and quota is consumed only by requests that pass every other check,
so denials no longer burn budget. `Broker` takes an injectable `clock`, which
is the seam a durable store will plug into.

**Not fixed:** persistence itself. That is a real design decision (SQLite?
Postgres? append-only file?) with schema, migration, and concurrency
consequences. Per the brief's rule 16, I am documenting it rather than
unilaterally bolting on a database. It is debt D-1 and the top production
blocker.

Tests covering the parts that were fixed: `TestF4DailyCapsAreActuallyDaily`.

---

## R-2 — Multi-process deployments multiply every cap. P0. OPEN.

Follows directly from R-1. Two workers means two independent counters. Any
forking server, any horizontally scaled webhook, any cron-invoked script — each
gets a full quota.

**Current honest guidance:** run exactly one Kynd process. This is stated in
the README and RELEASE_PLAN. It is a real constraint, not a preference.

Fixing this requires a shared counter store with atomic increment. Same debt
item as R-1.

---

## R-3 — Idempotency is in-process only. P1. PARTIALLY FIXED.

Before: no idempotency at all. A retried n8n delivery charged the card twice —
confirmed by execution.

Now: `idempotency_key` is honoured. A repeat returns the cached result without
re-invoking the handler and without consuming quota. Keys cannot be reused
across capabilities. **Failures are deliberately not cached**, so a transient
error remains retryable — caching a failure would be worse than not deduping.

Remaining gap: the cache is in memory and unbounded. It does not survive
restart (R-1) and grows with distinct keys. Bounding it is easy; making it
durable is the same debt as R-1.

Tests: `TestF11Idempotency` (5 cases), `test_webhook_idempotency_key_is_honoured`.

---

## R-4 — Failure was indistinguishable from success in the audit trail. P1. FIXED.

See ARCHITECTURE_AUDIT F-5. `ExecutionRecord` now carries `status` —
`allowed` / `denied` / `failed` — plus `error`, alongside the original
`allowed` boolean which retains its "policy permitted" meaning.

Tests: `TestF5FailedExecutionsNotAuditedAsSuccess`.

---

## R-5 — Unbounded memory growth. P2. FIXED.

Both logs grew forever, retaining full parameter payloads (verified: a 1 MB
blob was held indefinitely). A long-running webhook leaked memory proportional
to traffic.

Fixed: both are bounded `deque`s, default 10,000 entries, configurable.

**Tradeoff, stated plainly:** bounding the audit log means old entries are
dropped. For an in-memory log that dies on restart anyway this is strictly
better than unbounded growth, but it reinforces that this is not a durable
audit system. Anyone who needs a real audit trail must ship entries out to
durable storage as they are produced.

Tests: `TestF12BoundedLogs`.

---

## R-6 — Concurrency. P2. FIXED (defence in depth).

`Broker.request` read the call count and incremented it later with no lock —
textbook check-then-act.

**I could not reproduce an exploit.** Three attempts, documented in
ARCHITECTURE_AUDIT F-10, including 64 threads on a barrier and an I/O-shaped
delay inside the capability lookup. CPython's GIL plus a very narrow window
kept it correct every time.

Fixed anyway with a `threading.Lock`, because the window widens the moment the
constitution or counter is backed by I/O, and vanishes on a free-threaded
build. Labelled defence in depth, not a reproduced exploit.

Test: `test_cap_holds_with_64_concurrent_callers` asserts the invariant under
contention.

---

## R-7 — External integration resilience. N/A by design.

The brief asks about timeouts, retries, backoff, and partial responses for
every external integration. The honest answer:

**Kynd makes no outbound network calls.** No HTTP client exists in the package.
Tool handlers are supplied by the caller and own all network I/O, retries, and
timeouts.

This is the right boundary and I am not adding a retry framework nobody asked
for. What Kynd owes the caller instead is:

- a failed handler is recorded as `failed`, not silently swallowed — done (R-4)
- a retry after failure is safe and does not double-consume quota — done (R-3)
- a retry with the same idempotency key does not double-execute — done (R-3)

The one place Kynd *is* the network boundary is the inbound webhook, and that
is covered in SECURITY_AUDIT S-1/S-3.

**UNVERIFIED:** Langfuse and n8n interoperability. Neither has ever been
exercised against a real instance. If Langfuse's `observe` API has changed, the
wrapper breaks at import — the fallback only covers `ImportError`, not a
signature change.

---

## R-8 — Process interruption mid-operation. P2. ACCEPTED.

If the process dies between the broker allowing a call and the handler
completing, the quota is consumed but the side effect may or may not have
happened. There is no write-ahead record and no reconciliation.

This is inherent to any system without durable state and resolves with R-1.
Until then it is a known, documented limitation. With in-memory counters the
whole quota resets on that same restart anyway, so the inconsistency is
academic today — it becomes real the moment persistence lands, and the design
for R-1 must account for it.

---

## Failure-mode summary

| Scenario | Fails safely? | Visible? | State preserved? | Retry safe? |
|---|---|---|---|---|
| Malformed constitution | yes — refuses at load | yes, named error | n/a | yes |
| Unknown rule type | yes — denies | yes | yes | yes |
| Bad amount type | yes — denies | yes | yes | yes |
| Negative amount | yes — denies | yes | yes | yes |
| Unregistered capability | yes — denies | yes | yes | yes |
| Handler raises | yes — records `failed`, re-raises | yes | yes | yes, quota consumed |
| Duplicate request w/ key | yes — replays cached | yes | yes | yes |
| Duplicate request w/o key | **no — executes twice** | yes | yes | n/a |
| Oversized webhook body | yes — 413 | yes | yes | yes |
| Unauthenticated webhook | yes — 401 | yes | yes | n/a |
| Process restart | **no — caps and audit reset** | **no** | **no** | n/a |
| Second worker process | **no — caps multiply** | **no** | **no** | n/a |

The three `no`s in that table are the production blockers, and all three are
the same root cause: no durable state.
