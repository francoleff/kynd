# TECHNICAL DEBT REGISTER — Kynd Runtime

Ranked. Priorities are not inflated: P0 means it blocks production, and only
items that genuinely block production carry it.

Findings F-1 … F-13 (ARCHITECTURE_AUDIT.md) were fixed this pass and are not
repeated here. This register is what remains.

---

## D-15 — `ruff format --check` not yet gated in CI. P3. NEW.

**PROBLEM.** No `ruff format` baseline existed for this repo before D-11. Running
`ruff format --check` now flags 18 of ~20 files as "would be reformatted" —
purely cosmetic line-wrapping differences from the newly-added `[tool.ruff]`
config, zero behavior change.

**DECISION.** Not gated in this pass. Forcing a mass reformat here would
produce a large, low-signal diff across already-reviewed code, which is
explicitly out of scope for D-11 ("do not change application behavior unless
CI exposes a genuine defect" — formatting preference is not a defect).
`ruff check` (lint) is gated and catches real bugs; `ruff format` catches
none.

**RECOMMENDATION.** Adopt `ruff format` as its own deliberate, reviewed pass:
run `ruff format src tests` once, review the diff as a single formatting-only
PR, then add `ruff format --check` to CI as a permanent gate.

**PRIORITY. P3.**

---

## D-11 — CI has never run. **CLOSED 2026-09-01.**

**PROBLEM (as of the prior audit).** `.github/workflows/ci.yml` existed but
had never executed on a real GitHub Actions runner. Every gate in it —
tests, lint, security, build — was aspirational, not proven.

**RESOLUTION.** Four real pushes, four real runs on `francoleff/kynd-runtime`.
Found and fixed two genuine CI-config bugs (`pip-audit --strict` incompatible
with `--skip-editable`; no `[tool.ruff]` config existed, causing 61 mostly-
noise findings mixed with several real ones). Added explicit persistence,
multi-process, and flake-check steps beyond the blanket `pytest -q`. Added a
`build` job that installs the actual wheel into a clean venv. Proved the
release gate genuinely blocks a broken change (run 33502354764: a deliberate
failing assertion turned `test (3.11)`/`test (3.12)` red) and genuinely
un-blocks once fixed (run 33502462685: full green). Full detail, including
every run ID, in `docs/engineering/D11_CI_VERIFICATION.md`.

**PRIORITY. Was P0. Closed — no P0 items remain in this register.**

---

## D-1 — No durable state. **CLOSED 2026-08-31.**

**PROBLEM (as of the prior audit).** Call counts, audit log, execution log, and
idempotency keys were all in-process memory. A restart reset every daily cap
and erased the audit trail.

**RESOLUTION.** `SqliteStore` (`src/kynd_runtime/persistence.py`), wired into
`Broker`/`GovernanceGate`/`Executor` via an optional `store=` parameter.
Proven with a real restart (deleted Python objects, reopened the same file),
real multi-process concurrency (8 actual OS processes, not threads), and
concurrent idempotency races (10-30 threads on one key). Full detail,
including the two bugs found and fixed while proving it, in
`docs/engineering/D1_IMPLEMENTATION.md`.

**PRIORITY. Was P0. Closed, not removed from history** — the full writeup
stays as the record of what was wrong and how it was verified fixed.

---

## D-2 — `approval_id` is never verified. **CLOSED 2026-08-31.**

**PROBLEM (as of the prior audit).** `require_param: approval_id` checked only
that the key was present. Its value was never validated.

**RESOLUTION.** `require_param` rules gained `verify: approval`. With a store
configured, the approval is looked up, checked for existence/expiry/revocation
/capability match/target match/amount cap/use count, and atomically consumed
exactly once. Without a store, `verify: approval` fails closed — presence is
never treated as validity. Adversarially tested: 12 forged/malformed approval
shapes, cross-capability reuse, a 50-thread race on a one-time approval — all
correctly denied except the single legitimate winner in the race. Full detail
in `docs/engineering/D1_IMPLEMENTATION.md`.

**PRIORITY. Was P0. Closed.**

---

## D-12 — Idempotency stale-window is fixed, not per-capability. P2. NEW.

**PROBLEM.** `SqliteStore(stale_pending_seconds=300)` is one value for the
whole store. A capability whose handler legitimately takes longer than 5
minutes has no per-call override for how long a "pending" claim is treated as
abandoned before becoming reclaimable.

**IMPACT.** Low today — most tool calls (HTTP requests, DB writes) complete in
seconds. Would matter for a capability wrapping a long-running job.

**RECOMMENDATION.** Add an optional per-capability override, sourced from the
constitution, when a real long-running capability is added.

**PRIORITY. P2.**

---

## D-13 — No retention policy for durable tables. P2. NEW.

**PROBLEM.** `idempotency_keys`, `approvals`, `audit_log`, and `execution_log`
in SQLite grow without bound — the in-memory views are capped (F-12, prior
pass) but the durable copies are not.

**IMPACT.** Low at current scale. Matters for a long-running, high-volume
production deployment — the DB file grows forever.

**RECOMMENDATION.** A scheduled cleanup (`DELETE FROM audit_log WHERE ts <
?`) or a configurable retention window on `SqliteStore`. Not urgent; do not
build it speculatively before real volume data justifies a specific policy.

**PRIORITY. P2.**

---

## D-3 — `ControlPlane` dead parallel API. **CLOSED 2026-09-01 (DELETED).**

**PROBLEM (as found).** `ControlPlane` offered `evaluate()` + `execute()`
with different semantics from `Executor` (returns vs raises), had no
`ToolRegistry` (could not invoke a real tool handler), no `store=`
(no persistence, no approval verification, no idempotency), and —
critically — `ControlPlane.execute()` called only `Broker.request()` and
**never called `GovernanceGate.check()`**. A caller using that API believing
it was governed execution got zero hard-rule enforcement: a `block_action_type`
rule, a `require_param`/approval check, all of it — silently skipped.

**EVIDENCE OF DEAD STATUS (proven, not assumed):**
- Not exported from `kynd_runtime.__init__` (`"ControlPlane" in
  open("src/kynd_runtime/__init__.py").read()` → `False`).
- Not referenced anywhere in `README.md` or `examples/`.
- Not referenced in `pyproject.toml` (no entry points).
- Its only consumer was `tests/test_control_plane.py`, which exercised the
  class in isolation and never crossed paths with `Executor`.
- No live governance/approval/idempotency bypass existed via this class: it
  had no `ToolRegistry`, so it could never actually invoke a real side
  effect. The danger was documentation/API-contract risk (a developer
  reading `evaluate()`+`execute()` and reasonably assuming that combination
  was the governed path), not a live production bypass.
- This was independently confirmed as F-10 in `ARCHITECTURE_AUDIT.md`
  during the original hardening pass — the gate-skip was known and
  documented before D-3 even opened as its own item.

**DECISION: DELETE.** Not consolidate (nothing in `ControlPlane` did
anything `Executor` doesn't already do correctly) and not retain (it had no
distinct architectural responsibility — it was a strictly worse, partial
duplicate of `Executor`'s gate+broker wiring, missing the approval/
idempotency/persistence/tool-dispatch stages entirely).

**RESOLUTION.** Removed the `ControlPlane` class and its 6-test file.
`control_plane/__init__.py` now re-exports only the underlying building
blocks (`Constitution`, `GovernanceGate`, `Broker`, `Action`, etc.) for
callers who need direct access to one piece — it no longer offers its own
execution facade. `Executor` remains the single governed execution path.
162 tests pass (168 − 6 removed `ControlPlane`-only tests); mypy/ruff clean.

**PRIORITY. Was P2/P1 (escalated as the top remaining risk after D-1/D-6/
D-11 closed). Closed.**

---

## D-4 — `max_amount` is checked in two places. P3.

**PROBLEM.** Both gate and broker enforce the amount cap, with different
messages.

**IMPACT.** None functionally — both now read the same
`constitution.effective_max_amount`, so they cannot disagree. It is duplicated
work and a future divergence risk.

**RISK.** Low. Arguably defence in depth: if one layer is bypassed the other
still holds.

**RECOMMENDATION.** Leave it. Documented as intentional.

**PRIORITY. P3.**

---

## D-5 — Langfuse integration is unverified. P2.

**PROBLEM.** `observability.py` has never run against a real Langfuse instance.
The fallback only catches `ImportError`, so a changed `observe` signature breaks
at import rather than degrading.

Fixed this pass: `TracedExecutor` no longer snapshots the logs in `__init__`
(which shadowed the proxy with permanently stale copies), and it now forwards
`action_type`.

**IMPACT.** Tracing may not work at all in production. Nobody would know.

**EFFORT.** Low — spin up Langfuse locally, run one traced execution.

**RECOMMENDATION.** Either verify it, or mark it experimental in the README.
Also add `langfuse` to `[project.optional-dependencies]`; it is imported but
undeclared.

**PRIORITY. P2.**

---

## D-6 — No static type checking. P1.

**PROBLEM.** No mypy or pyright configuration, no CI gate. The codebase's entire
job is validating untyped dicts from YAML and model output.

**IMPACT.** The class of bug this catches is exactly the class that hid here —
F-6 was a `str` reaching a `float` comparison, which a type checker inspecting
`params.get("amount")` would have flagged as `Any` flowing into arithmetic.

**EFFORT.** Low to add, medium to reach clean.

**RECOMMENDATION.** Add mypy in non-strict mode, gate in CI, tighten over time.

**PRIORITY. P1.**

---

## D-7 — `ToolRegistry.register` silently overrides. **CLOSED 2026-09-05.**

**PROBLEM (as found).** Re-registering a capability replaced the handler with
only a `logger.warning`. Confirmed: the second registration won, silently.

**RESOLUTION.** `register()` gained a keyword-only `replace: bool = False`.
Registering an already-registered capability without `replace=True` now
raises `CapabilityAlreadyRegisteredError` and leaves the existing handler in
place — no partial mutation. The one legitimate intentional-swap call site in
the test suite now passes `replace=True` explicitly. 4 new regression tests
in `TestD7ToolRegistryRejectsHijack` (`tests/test_regressions_hardening.py`):
duplicate rejected + original handler still runs, explicit replace still
works, first-time registration unaffected, unregister-then-register needs no
flag. Full detail in `docs/engineering/REMEDIATION_REPORT.md`.

**PRIORITY. Was P3. Closed.**

---

## D-8 — No property-based tests. P3.

**PROBLEM.** All tests are example-based.

**RECOMMENDATION.** The invariant worth expressing as a property: *for any valid
constitution and any sequence of actions, executed side effects never exceed the
declared caps and never include a blocked action type.* `hypothesis` would
express it well, but it is a new dependency — decide deliberately.

**PRIORITY. P3.**

---

## D-9 — Denial logging is unbounded in volume. P3.

**PROBLEM.** One WARNING per denial. A benchmark of ~100,000 denials produced
12 MB of stderr.

**IMPACT.** Log volume under a denial-heavy workload (e.g. a misconfigured agent
retrying a blocked action in a loop).

**RECOMMENDATION.** Do not remove the logs — denials must be visible. Document
log rotation in deployment; consider rate-limiting identical consecutive
denials.

**PRIORITY. P3.**

---

## D-10 — `pyproject.toml` claims Python 3.10 and 3.12 support. P2.

**PROBLEM.** Only 3.11.15 has ever run this code. The system `python3` is 3.9.6
and cannot run it at all.

**IMPACT.** A user on 3.10 or 3.12 may hit an unknown failure. The CI matrix
covers all three but has never executed.

**RECOMMENDATION.** Run CI. Until then treat 3.10/3.12 as **UNVERIFIED**.

**PRIORITY. P2.**

---

## D-11 — CI has never run. P1.

**PROBLEM.** `.github/workflows/ci.yml` is written but no runner has executed
it. Its lint, security, and coverage gates are aspirational: `ruff`, `bandit`,
and `pip-audit` are not installed locally, so their results are **UNVERIFIED**.

**IMPACT.** The gates may fail immediately on first run. Quoting them as
"passing" would be a fabrication.

**RECOMMENDATION.** Push and let it run. Expect a first-run cleanup pass on
ruff findings.

**PRIORITY. P1.**

---

## PRODUCTION READINESS SCORE

Scored 0–10. "Current" is after this hardening pass. Justified, not generous.

| Dimension | Before hardening | After hardening (4cffc91) | After D-1 (this pass) | Target | Note |
|---|---|---|---|---|---|
| Architecture | 7 | 8 | 8 | 9 | Layering unchanged and still good — persistence added via an optional seam, not a rewrite |
| Correctness | 3 | 8 | 8 | 9 | Unaffected by D-1 (D-1 fixed reliability/security, not logic correctness) |
| Security | 2 | 7 | **8** | 9 | D-2 closed: approval presence no longer equals approval |
| Reliability | 3 | 6 | **8** | 9 | D-1 closed: caps/audit survive restart, proven multi-process safe |
| Testing | 4 | 8 | **8** | 9 | 127 → 168 tests; still no property tests, CI still unrun |
| Performance | 7 | 8 | 8 | 8 | Unaffected; SQLite overhead not yet benchmarked (new: see below) |
| Observability | 4 | 7 | 7 | 8 | Durable audit/execution log queryable via store, not yet exposed as a CLI/API |
| Data integrity | 2 | 4 | **8** | 9 | Transactional migrations, atomic quota/approval consumption |
| Deployment | 1 | 5 | 5 | 8 | Still no container; single-process constraint now OPTIONAL (multi-process works with a store) rather than mandatory |
| Recovery | 1 | 3 | **6** | 8 | State survives restart; no backup/restore *procedure* for the SQLite file itself yet |
| Documentation | 3 | 8 | 8 | 9 | D1_IMPLEMENTATION.md added; README not yet updated for the new store= parameter (see D-14 below) |
| Maintainability | 7 | 8 | 8 | 9 | One new module, zero new dependencies, backward compatible |
| AI safety | 3 | 7 | **9** | 9 | Approval verification closes the last major gap |

```
SCORE AFTER 4cffc91:  6.7 / 10
SCORE AFTER D-1:      7.6 / 10
SCORE AFTER D-11:     8.1 / 10
SCORE AFTER D-6:      8.4 / 10
SCORE AFTER D-3:      8.4 / 10
TARGET:               8.8 / 10

BLOCKERS CLEARED:
  D-1  durable state — CLOSED
  D-2  approval verification — CLOSED
  D-11 CI has never run — CLOSED (4 real GitHub Actions runs; see
       docs/engineering/D11_CI_VERIFICATION.md for every run ID)
  D-6  static type safety — CLOSED (mypy in CI, deliberate-failure proven)
  D-3  ControlPlane dead parallel API — CLOSED (deleted, not consolidated;
       it never called GovernanceGate.check() and had no live bypass path
       because it had no ToolRegistry, but was a real documentation/API-
       contract risk)

BLOCKERS REMAINING:
  none. No open P0 or escalated P1 items in this register as of 2026-09-01.

RISKS:
  Stale-pending idempotency window (300s default) is a documented, unavoidable
    tradeoff for coordinating an external non-transactional side effect
  SQLite is single-host; a genuine multi-host deployment needs a different store
  ruff format not yet gated (D-15) — cosmetic only, deliberately deferred
  NFS-backed storage still explicitly out of scope (documented, not a gap)

RESOLVED BY D-11 (previously UNVERIFIED, now genuinely confirmed):
  Python 3.10 / 3.12 support — real CI matrix, both green

REMAINING WORK, in order:
  1. Adopt ruff format as its own reviewed pass, then gate it (D-15)
  2. Retention policy if/when real volume justifies it (D-13)
  3. Idempotency stale-window per-capability override (D-12)
  4. Langfuse integration verified against a real instance (D-5)
```


### The honest one-line summary

Before this pass Kynd promised governance it did not deliver — a constitution
saying "never delete" while `delete_all_customers` executed. That specific
class of lie is now gone and locked down by tests that were proven to fail
against the old code. What remains is not a correctness problem; it is that the
runtime forgets everything when the process ends.
