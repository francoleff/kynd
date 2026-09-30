# PRODUCTION READINESS — Kynd Runtime

Assessed 2026-08-31, after the hardening pass described in ARCHITECTURE_AUDIT.md.

## BASELINE (before any changes)

```
Build:          PASS   — pip install -e ".[dev]" into .venv (py3.11.15)
Tests:          PASS   — 62 passed in 0.19s
Typecheck:      ABSENT — no mypy/pyright config, no CI step
Lint:           ABSENT — no ruff/flake8 config
Format:         ABSENT — no black/ruff-format config
Integration:    PARTIAL — tests/test_executor_integration.py is in-process only
E2E:            ABSENT — examples/e2e_demo.py is a demo script, not an assertion
Security:       ABSENT — no pip-audit, no bandit, no secret scanning
Deployment:     ABSENT — no Dockerfile, no service definition, no runbook
Documentation:  INACCURATE — README described a 5-phase architecture that
                             does not exist in code
CI:             ABSENT — no .github/
LICENSE:        MISSING — pyproject declares MIT, no LICENSE file present
Known failures: none reported by the suite

Hidden failures the green suite did NOT catch: 13 (see ARCHITECTURE_AUDIT.md),
including 5 rated P0. The most severe: the primary hard-rule type
`block_action_type` never fired through the executor.
```

## CURRENT (after hardening)

```
Build:          PASS   — unchanged
Tests:          PASS   — 127 passed in 4.18s (62 original + 65 regression)
Typecheck:      ABSENT — still not wired (debt D-6)
Lint:           GATED  — ruff check + format in CI (not yet run locally: no ruff installed)
Integration:    PASS   — webhook tests now bind a real socket and speak real HTTP
E2E:            PARTIAL — examples run in CI as smoke tests
Security:       GATED  — pip-audit + bandit in CI; UNVERIFIED locally (not installed)
Deployment:     DOCUMENTED — docs/engineering/RELEASE_PLAN.md; no container yet
Documentation:  ACCURATE — README rewritten against the implementation
CI:             PRESENT — .github/workflows/ci.yml (UNVERIFIED: never executed on
                          GitHub; no runner has run this file)
LICENSE:        PRESENT — MIT
```

## Verification status of every claim in this document

| Claim | How verified |
|---|---|
| 127 tests pass | `.venv/bin/python -m pytest tests/ -q` → `127 passed in 4.18s` |
| Regression tests catch the old bugs | `git stash push -- src/` then re-run → `44 failed, 10 passed, 8 errors` |
| Examples run clean | `python examples/{e2e_demo,send_email,hardening_demo}.py` → exit 0 |
| Webhook rejects unauthenticated calls | real HTTP request to a bound socket → 401, zero side effects |
| CI passes | **UNVERIFIED** — the workflow has never been run by GitHub Actions |
| ruff / bandit / pip-audit clean | **UNVERIFIED** — none of these are installed locally |
| Langfuse tracing works | **UNVERIFIED** — never tested against a real Langfuse instance |
| n8n interoperates | **UNVERIFIED** — never tested against a real n8n instance |
| Behaviour on Python 3.10 / 3.12 | **UNVERIFIED** — only 3.11.15 was exercised |

## Is it production ready?

**No — but it is no longer dangerous.**

The distinction matters. Before this pass, Kynd would have given an operator a
written guarantee ("no destructive actions", "spend capped at $500") that the
code did not deliver. Shipping that is worse than shipping nothing, because it
substitutes false confidence for caution.

That specific class of defect is now fixed and regression-tested.

What still blocks a paying-customer launch is not correctness of the policy
logic — it is that **the runtime has no memory**:

### Blockers

- **B-1 (P0). No durable state.** Call counts, audit log, and idempotency keys
  are all in-process. A restart resets every daily cap to zero and erases the
  audit trail. An audit log that does not survive a crash is not an audit log.
  A cap that resets on restart is not a cap. This is the single largest gap
  between "the logic is right" and "you can sell this".
- **B-2 (P0). No multi-process story.** Two workers, or a webhook behind any
  process manager that forks, each keep their own counters. `max_calls_per_day:
  10` becomes 10 × N workers. The current code is only safe as a single process.
- **B-3 (P1). CI is unproven.** The workflow is written but has never run.
  Until a real run goes green, treat every gate in it as aspirational.
- **B-4 (P1). No typecheck.** A codebase whose entire job is validating untyped
  dicts from YAML and models has no static type gate.

### Risks accepted for now

- **R-a.** Constitution is loaded once and never reloaded. Editing the YAML
  requires a restart. Acceptable and documented; a hot-reload path would add a
  consistency problem nobody has asked for yet.
- **R-b.** `verification.run_command(shell=True)` remains available. It is now
  opt-in and documented rather than the default. The caller owns that risk.
- **R-c.** The capability-name verb match (`delete` blocks `delete_users`) is a
  heuristic. It is deliberately conservative — it errs toward blocking — but it
  is not a substitute for naming capabilities carefully. Documented in SECURITY.

## Honest summary

The governance core is now correct, tested against its own failure modes, and
fails closed in every path I could find. The packaging around it — persistence,
deployment, proven CI — is not there yet.

Score and target: see the end of TECHNICAL_DEBT.md.
