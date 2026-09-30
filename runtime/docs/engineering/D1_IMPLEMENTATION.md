# D-1 IMPLEMENTATION — Durable Governance + Verified Approvals

Closes the two P0 blockers from `TECHNICAL_DEBT.md` (D-1: no durable state,
D-2: `approval_id` not verified). Implemented 2026-08-31, on top of the
2026-08-31 hardening pass (commit `4cffc91`).

## What was built

One new module, `src/kynd_runtime/persistence.py` — a SQLite-backed store
(`SqliteStore`) that owns four things: daily call counts, the audit and
execution logs, idempotency claims, and a real approval lifecycle. `Broker`,
`GovernanceGate`, and `Executor` each take an **optional** `store=` parameter.
Passing none reproduces the exact pre-D-1 in-memory behavior — every one of
the 127 pre-existing tests runs unmodified and passes.

**Why SQLite, not a new service.** The deployment model documented in
`RELEASE_PLAN.md` is a single-host library, optionally fronted by one loopback
webhook process — not a distributed system. SQLite with WAL mode and
`BEGIN IMMEDIATE` write locking gives real atomic cross-process coordination
on that model, using only the standard library (`pyproject.toml` gained zero
new dependencies). Building a Postgres-backed service, a Redis lock, or any
network component would have solved a deployment model Kynd does not have —
exactly the "invent distributed infrastructure nobody asked for" the mission
explicitly forbade.

## Architecture changes

None to the layering. `Constitution → GovernanceGate → Broker → ToolRegistry →
Executor` is unchanged. What changed is that `Broker` and `GovernanceGate` can
now delegate their state to a shared store instead of an in-process dict:

```
Executor(constitution, registry, store=SqliteStore("kynd.db"))
        │
        ├─ GovernanceGate(constitution, approval_store=store)
        │     └─ require_param rules with `verify: approval` call
        │        store.validate_approval() — read-only, side-effect free
        │
        ├─ Broker(constitution, store=store)
        │     └─ try_increment_call_count() — atomic check-and-increment
        │
        └─ store.claim_idempotency() / consume_approval() / append_execution()
```

`ControlPlane` (the documented-dead parallel API, D-3) was left untouched —
it still does not take a store, matching its existing "not the governed path"
status.

## Database / schema changes

Five tables, one migration (`schema_version=1`), applied inside a single
`BEGIN IMMEDIATE` transaction so a crash mid-migration cannot leave a
half-applied schema — confirmed by a test that injects a failing statement
into the migration and verifies `schema_version` did not advance.

| Table | Purpose |
|---|---|
| `schema_version` | Migration tracking |
| `call_counts` | `(day, capability) -> count`, PK on the pair |
| `audit_log` | Every broker attempt, allow or deny |
| `execution_log` | Every executor attempt, allowed/denied/failed |
| `idempotency_keys` | `key -> status (pending/completed/failed)`, result JSON |
| `approvals` | Full approval record: capability, scope, expiry, use count |

Fresh install and reopen-of-current-schema are both tested (`TestMigrations`).
A concurrent first-open by 10 threads against a brand-new file is also tested
and does not corrupt the schema — the migration check-then-lock pattern (cheap
unlocked read, re-check under `BEGIN IMMEDIATE`, migrate only if still behind)
means a normal reopen never even takes a write lock.

## Security changes

**D-2 closed.** `require_param` rules gained an optional `verify: approval`
flag. Without it, behavior is unchanged (presence of the param is enough —
backward compatible). With it:

1. The value must be a non-empty string.
2. If no `store` is configured, the gate **denies** — a present `approval_id`
   is never silently treated as valid just because nothing exists to check it
   against. This is the direct fix for the original bug: a model emitting
   `{"approval_id": "abc123"}` used to pass; now it is rejected unless a real
   approval store says otherwise.
3. With a store, the approval is looked up and checked: exists, not revoked,
   not expired, matches the requested capability, matches the target (if the
   approval was scoped to one), amount within the approval's own cap, and use
   count under its limit.
4. The gate's check is read-only (`validate_approval`) — actual consumption
   (`consume_approval`) happens once, atomically, in the executor, only after
   *every* other check (gate + broker) has passed. This prevents a denied
   action from burning a one-time approval, and prevents two concurrent
   requests from both believing they hold the last use.

## Approval model

```python
approval_id = store.issue_approval(
    capability="charge_card",
    action_type=None,        # optional scope
    max_amount=500.0,        # optional spend ceiling for THIS approval
    target=None,              # optional target scope
    ttl_seconds=3600.0,       # default 1 hour; None = never expires
    max_uses=1,               # default one-time; None = unlimited until expiry
    issued_by=None,           # optional attribution string
)
```

Token: `secrets.token_urlsafe(32)` — 256 bits of entropy, unguessable.
Consumption is one atomic `UPDATE ... WHERE approval_id = ? AND revoked = 0
AND (expires_at IS NULL OR expires_at > ?) AND (max_uses IS NULL OR
use_count < max_uses)`. Only the UPDATE that actually changes a row commits;
every other concurrent consumer's UPDATE affects zero rows and is told the
current (now-false) state. This is what makes "50 threads race a one-time
approval" produce exactly one winner (verified — see Tests Executed).

There is intentionally **no "human clicked approve" UI** in this repo — that
is out of scope for a library. `issue_approval` is the seam: a real deployment
wires it behind whatever approval flow it has (Slack button, email link, admin
panel) and only calls `issue_approval` after a human genuinely approved.

## Idempotency model

`claim_idempotency(key, capability)` returns one of:

- **new** — caller owns the key now; must call `complete_idempotency` or
  `fail_idempotency` when done.
- **completed** — a prior attempt finished; cached result returned, handler
  never re-invoked.
- **in_progress** — another caller (possibly another process) is currently
  executing; the executor polls `wait_for_idempotency` for it to resolve.
- **conflict** — the key was already used for a *different* capability;
  refused outright rather than silently reusing it.

A **failed** attempt is never cached as a success — `fail_idempotency` marks
the row `failed`, and the next claim for that key is immediately reclaimable,
giving the retry a genuine new attempt (verified: a handler that fails once
then succeeds is retried correctly, including across a simulated restart).

A **pending** claim older than `stale_pending_seconds` (default 300s) is also
reclaimable — this is the practical bound on "the owning process crashed and
will never call complete/fail." See Crash Recovery Model for the honesty
statement about what that boundary does and does not guarantee.

## Crash recovery model

What is proven to survive a process death (tested by literally deleting the
Python objects — no `finally`, no graceful shutdown — and opening a fresh
`SqliteStore` on the same file):

- Call counts (governance caps hold across restart)
- The audit log
- The execution log
- Idempotency claims and their results
- Approval records and their consumption

**What is explicitly NOT claimed:** exactly-once execution of the external
side effect itself. If a process dies between "handler ran" and "result
recorded," Kynd cannot know whether the side effect happened. A retry after
that specific crash window will re-invoke the handler. This is a mathematical
limit of coordinating a non-transactional external system (an SMTP send, a
Stripe charge) from a local transactional store — not a bug, and not fixable
without making the tool handlers themselves transactional participants, which
is out of scope and would be genuine architectural overreach.

What Kynd *does* guarantee, and what is actually tested:
- A governance decision (cap consumed, approval consumed) is never
  double-applied, regardless of restarts or concurrent callers.
- A given idempotency key converges on exactly one recorded outcome that
  every caller — before or after a restart — observes identically.
- The **stale-pending window** (default 300s) is the honest, documented
  boundary: a crash discovered within that window blocks a duplicate
  correctly; a crash discovered after it allows a reclaim that may re-invoke
  the handler. This tradeoff is unavoidable without a heartbeat/lease
  mechanism, which would be more infrastructure than this deployment model
  justifies.

## Tests added

`tests/test_persistence_d1.py` — 41 tests, organized to match the mission's
own checklist:

| Class | Count | Covers |
|---|---|---|
| `TestRestartPersistence` | 5 | call counts, audit, execution log, idempotency, approvals all survive a real reopen |
| `TestDailyRollover` | 2 | UTC date rollover, old-day rows don't leak into new day |
| `TestMultiProcessQuotaSharing` | 1 | 8 threads sharing one store, cap holds exactly |
| `TestDuplicateIdempotencyKey` | 2 | same key returns cached result; cross-capability reuse refused |
| `TestConcurrentDuplicateRequests` | 2 | 10 threads, same key, slow handler — exactly 1 invocation; quota consumed once |
| `TestRetryAfterCrash` | 3 | retry after failure is genuine; simulated crash before completion; hung owner produces a bounded error, not an infinite wait |
| `TestApprovalVerification` | 15 | fake/forged/expired/revoked/mismatched-capability/mismatched-target/over-amount/consumed/malformed/missing/unauthorized-scope/no-store-fails-closed/concurrent-race |
| `TestCrashRecovery` | 4 | transactional migration failure, missing parent dir, failed-status durability, retry-after-restart |
| `TestDatabaseUnavailable` | 2 | read-only directory, external exclusive lock times out instead of hanging |
| `TestMigrations` | 3 | fresh install, reopen-is-noop, 10 concurrent first-opens |
| `TestFullPipelineWithStore` | 1 | end-to-end realistic workflow including a restart mid-scenario |

Plus a manual, outside-pytest adversarial script (not committed — its
findings are folded into the tests above) that ran real break attempts:
12 forged/malformed approval_id shapes, a genuine cross-capability approval
reuse attempt, a 50-thread race on a one-time approval, a 30-thread race on
one idempotency key, and a crash-then-reclaim sequence. All five categories
failed to break the system; the results are what's now encoded as the tests
above.

**Real multi-process proof, not just threads.** During development I ran 8
actual separate OS processes (not threads — `python _mp_worker.py &` × 8)
against one fresh SQLite file with `max_calls_per_day: 5`. Three consecutive
runs: total allowed calls was exactly 5 every time, 0 crashes, 0 corrupted
schema. This found two real bugs (see below) that no thread-based test would
have caught, because threads share a process and its already-open file
descriptors — real process starts race the file's very first creation and WAL
conversion in ways threads cannot.

## Bugs found and fixed *while building this*

Honesty requirement: report what actually broke, not just what was designed.

1. **`busy_timeout` was set after `journal_mode=WAL`.** A concurrent process's
   first connection could hit "database is locked" immediately instead of
   waiting, because the pragma that makes SQLite wait wasn't in effect yet
   when the lock-contending pragma ran. Found by the 8-real-process test.
   Fixed: `busy_timeout` set first, unconditionally, before any other pragma.
2. **First-ever WAL conversion on a brand-new file can still race.** Even with
   `busy_timeout` set correctly, the very first `sqlite3.connect()` +
   `PRAGMA journal_mode=WAL` on a file that doesn't exist yet is a distinct
   exclusive-lock event across processes. Fixed: bounded retry (5 attempts,
   exponential backoff) around the whole connect sequence.
3. **Migration always took a write lock, even when nothing needed migrating.**
   Meant every single store open contended for the write lock unnecessarily.
   Fixed: cheap unlocked read first; only take `BEGIN IMMEDIATE` if actually
   behind, then re-check under the lock (another process may have migrated in
   the gap).
4. **Blind `ROLLBACK` in exception handlers.** Several methods wrapped
   `BEGIN IMMEDIATE ... COMMIT` in `try/except Exception: conn.execute
   ("ROLLBACK"); raise`. If the exception was `BEGIN IMMEDIATE` itself failing
   (e.g. a lock timeout), the `ROLLBACK` had nothing to roll back and raised
   its own `sqlite3.OperationalError: cannot rollback - no transaction is
   active`, masking the real error. Found by `test_locked_database_times_out
   _rather_than_hanging_forever`, which asserted on the *original* error and
   got the masking one instead. Fixed with a `_safe_rollback()` helper that
   tolerates "no transaction active."

All four were caught by tests before being reported as fixed, not the other
way around.

## Tests executed

```
$ .venv/bin/python -m pytest tests/test_persistence_d1.py -v
41 passed in 2.88s

$ .venv/bin/python -m pytest tests/ -q     (x3 consecutive runs, flake check)
168 passed in 6.42s
168 passed in 6.28s
168 passed in 6.18s
```

168 = 127 pre-existing (untouched, unmodified) + 41 new. Zero regressions.

Real multi-process test (3 runs, 8 OS processes each, fresh DB each run):

```
run 1: worker6:5, others:0  -> TOTAL ALLOWED: 5 (cap=5)
run 2: worker3:4, worker7:1, others:0 -> TOTAL ALLOWED: 5 (cap=5)
run 3: worker2:4, worker3:1, others:0 -> TOTAL ALLOWED: 5 (cap=5)
```

Adversarial break-attempt script (manual, outside pytest):

```
1. Model-plausible forged approval_ids — 12 attempts, 0 bypassed
2. Cross-capability approval reuse — denied correctly
3. 50-thread race on a ONE-TIME approval — exactly 1 winner, 49 denied
4. 30-thread race on ONE idempotency key — exactly 1 real send
5. Crash immediately after claim, before completion — handled correctly
ALL ADVERSARIAL BREAK ATTEMPTS FAILED TO BREAK D-1
```

Examples (backward compatibility + new capability):

```
$ python examples/e2e_demo.py            exit 0 (unmodified, still passes)
$ python examples/send_email.py          exit 0 (unmodified, still passes)
$ python examples/hardening_demo.py      exit 0 (unmodified, still passes)
$ python examples/durable_governance_demo.py   exit 0 (new — restart proof)
```

## Tests failed

None, in the final state. Two were caught and fixed during development (see
"Bugs found and fixed" above) — both surfaced as test failures before the fix,
neither was worked around by weakening the test.

## UNVERIFIED

Same status as the prior hardening pass, unchanged by this work:

- **mypy / ruff / bandit / pip-audit**: not installed in this environment.
  No results are quoted for tools that were not run.
- **CI**: `.github/workflows/ci.yml` has still never executed on a real
  runner.
- **Python 3.10 / 3.12, Linux**: only CPython 3.11.15 on macOS/ARM was
  exercised.
- **NFS / network filesystem behavior**: the store assumes local-disk locking
  semantics. Explicitly documented in `persistence.py`'s module docstring as
  out of scope — do not put the DB file on NFS.
- **Behavior beyond ~8 concurrent processes**: tested at 8 (processes) and up
  to 50 (threads). SQLite's single-writer model means throughput, not
  correctness, is what would degrade further out; that was not load-tested.
- **Real-world approval issuance UX**: `issue_approval` is a library call.
  How a human actually triggers it (Slack, email, admin UI) is deployment-
  specific and was not built — by design, per the mission's "do not add
  unrelated features" instruction.

## Remaining risks

- **Stale-pending window (default 300s)** is a real, documented tradeoff, not
  a bug: a crash discovered after that window allows a reclaim that may
  re-invoke a handler whose side effect already happened. No mechanism here
  (or realistically, without a heartbeat/lease system) closes this
  completely. Tool handlers for genuinely irreversible actions should
  implement their own idempotency at the API level where possible (e.g.
  Stripe's own idempotency keys) as defense in depth.
- **Single-writer SQLite** is the right choice for this deployment model but
  is not infinitely scalable. If Kynd ever needs true multi-host operation
  (not just multi-process on one host), this store must be replaced — that is
  a deployment-model change, not a bug in this one.
- **`ToolRegistry.register` still silently overrides** (pre-existing D-7, not
  touched by this pass).
- **CI still unrun** (pre-existing D-11, not touched by this pass — running it
  was out of scope for D-1 specifically, though strongly recommended next).

## Updated P0/P1/P2 list

**P0 — CLOSED by this pass:**
- ~~D-1: no durable state~~ → `SqliteStore`, opt-in via `store=`, tested
  restart-survival, multi-process (both threaded and real-OS-process),
  concurrent idempotency, transactional migrations.
- ~~D-2: `approval_id` not verified~~ → real approval lifecycle: issue,
  validate, atomically consume, with expiry/revocation/one-time-use/scope
  matching, and fail-closed when no store is configured.

**P0 — still open (unchanged, not in this pass's scope):**
- D-11: CI has never run on a real runner.

**P1 (unchanged from prior pass, not touched by D-1):**
- D-3 ControlPlane dead parallel API
- D-6 no static type checking
- D-10 Python 3.10/3.12 claimed but unverified

**P2/P3 (unchanged):**
- D-4 duplicate max_amount check (still intentional, still fine)
- D-5 Langfuse unverified
- D-7 ToolRegistry silent override
- D-8 no property-based tests
- D-9 denial logging volume

**New, P2 (introduced by this pass, worth tracking):**
- D-12: `stale_pending_seconds` (default 300s) is a fixed value with no
  per-capability override. A capability with handlers that legitimately run
  longer than 5 minutes needs a larger value passed at `SqliteStore`
  construction; there's no per-call override yet. Low urgency — the default
  is generous for typical tool calls (HTTP requests, DB writes).
- D-13: No garbage collection for old `idempotency_keys` / `approvals` rows.
  They accumulate forever (audit/execution logs are similarly unbounded in
  the DB, though bounded in the in-memory view). For a long-running
  production deployment this needs a retention policy — not urgent at current
  scale, but should be tracked before very high-volume production use.

## Updated production readiness score

| Dimension | Prior | Now | Note |
|---|---|---|---|
| Reliability | 6 | **8** | Durable caps + audit; multi-process proven safe |
| Data integrity | 4 | **8** | Transactional migrations, atomic quota/approval consumption, restart-proof |
| Recovery | 3 | **6** | State survives restart; still no backup/restore *procedure* for the SQLite file itself (operator responsibility, documented, not automated) |
| AI safety | 7 | **9** | Approval presence is no longer sufficient; a model cannot forge, replay, or misuse an approval across capability/target/amount boundaries |
| Security | 7 | **8** | D-2 was the main remaining AI-safety gap; closed |

```
PRIOR OVERALL:  6.7 / 10
CURRENT OVERALL: 7.6 / 10
TARGET:          8.8 / 10

RELEASE GATE STATUS (as specified in the mission):
  NO P0 governance persistence blocker     -> CLEARED (D-1 closed)
  NO fake approval acceptance              -> CLEARED (D-2 closed, adversarially tested)
  NO process-local quota bypass            -> CLEARED (proven with real OS processes)
  NO known idempotency bypass              -> CLEARED (concurrent races tested and hold)

REMAINING BEFORE 8.8:
  D-11  run CI on a real runner
  D-6   add mypy
  D-3   deprecate/remove ControlPlane
  D-12/D-13  retention policy for durable tables (new, low urgency)
```

## The honest one-line summary

Before this pass, "governance" meant "until the process restarts" and
"approved" meant "a string was present." Neither is true anymore: caps and
audit survive a real restart and hold correctly across real concurrent
processes, and an approval must be genuinely issued, unexpired, unconsumed,
and scoped to the exact capability/target/amount being requested — proven by
adversarial tests that tried, and failed, to forge, replay, or race past it.
What remains is not a correctness gap in what was built; it's the honestly
documented edge of what a single-host SQLite store can promise about an
external side effect it does not control.
