# TESTING AUDIT — Kynd Runtime

## The finding that matters

**62 tests passed and 13 real defects were live, 5 of them P0.**

The suite was not lazy — it was well-written, fast, and mock-free in the core
path. It failed for a subtler and more instructive reason: **it tested each
component against the same assumptions the component was built with.**

The clearest example. `block_action_type` was completely broken through the
executor. Two test files touched it:

- `test_governance_gate.py` built `Action` objects by hand with `type="delete"`
  and `capability="send_email"` — distinct values. The gate handled that
  correctly, so the test passed.
- `test_executor_integration.py:79` called `executor.execute("delete", ...)` —
  a capability literally named `delete`. That is the single input shape where
  the bug is invisible.

Neither test ever asked the real-world question: *does a capability called
`delete_all_customers` get blocked by a rule that says `delete`?* The answer
was no, and nothing in 62 tests noticed.

**Lesson, recorded because it will recur:** unit tests that construct their own
inputs verify that a component is self-consistent. They do not verify that the
component receives the inputs the rest of the system actually sends it. The
gap between those two is where P0 bugs live.

---

## Baseline classification (62 tests, pre-hardening)

| Type | Count | Notes |
|---|---|---|
| UNIT | 47 | constitution, gate, broker, verifier |
| INTEGRATION | 11 | executor pipeline, control plane — all in-process |
| CONTRACT | 0 | — |
| E2E | 0 | `examples/e2e_demo.py` prints, asserts nothing |
| REGRESSION | 0 | no bug had a test |
| SECURITY | 0 | none |
| FAILURE | 3 | handler exception, missing file, bad YAML |
| PROPERTY | 0 | — |
| SMOKE | 0 | — |

Three tests were near-tautologies:

- `test_phase2.py:28-49` — "handler parses path correctly" never calls the
  handler. It re-implements `path.strip("/").split("/")` in the test body and
  asserts on that. It tests Python's `str.split`.
- `test_verification.py:70-74` — `test_command_succeeds` registers
  `lambda p: True` and asserts the result is `True`. It exercises no command.

These inflate the count without adding confidence. Left in place (rule 8: do
not disable tests) but noted.

---

## Current state (127 tests)

| Type | Count | Notes |
|---|---|---|
| UNIT | 47 | unchanged |
| INTEGRATION | 11 | unchanged |
| REGRESSION | 47 | `test_regressions_hardening.py`, one class per finding |
| SECURITY | 13 | real HTTP against a bound socket: authn, leakage, body limits |
| FAILURE | 6 | + failed-vs-denied distinction, non-finite amounts |
| CONCURRENCY | 1 | 64 threads on a barrier vs a cap of 1 |
| SMOKE | 2 | examples run in CI |

### The regression tests were verified to actually fail

A test that has never failed proves nothing. I stashed the fixed source and ran
the new suite against the original code:

```
$ git stash push -- src/
$ .venv/bin/python -m pytest tests/test_regressions_hardening.py -q
44 failed, 10 passed, 8 errors in 0.30s
```

44 failures and 8 errors against the old source; 127 passed against the new.
Each regression test is confirmed to bite.

---

## Critical-path matrix

| Priority | Invariant | Covered | Test |
|---|---|---|---|
| P0 | A blocked action type cannot execute | yes | `TestF1...` (5) |
| P0 | Spend cannot exceed the strictest cap | yes | `TestF2...` (4) |
| P0 | An unenforceable rule denies | yes | `TestF3...` (4) |
| P0 | An unregistered capability cannot execute | yes | `test_unknown_capability_raises` |
| P0 | A target outside the allowlist cannot be reached | yes | `test_broker_blocks_bad_target` |
| P0 | The webhook cannot be used without a token | yes | `TestWebhookSecurity` (3) |
| P0 | Model output cannot bypass the money cap | yes | `TestF6...` (5) |
| P1 | Daily caps roll over by date | yes | `TestF4...` (3) |
| P1 | A retry does not double-execute | yes | `TestF11...` (5) |
| P1 | A failure is not audited as a success | yes | `TestF5...` (2) |
| P1 | Verification cannot pass vacuously | yes | `TestF9...` (4) |
| P1 | A malformed constitution is refused at load | yes | `TestF13...` (13) |
| P2 | Logs are bounded | yes | `TestF12...` (2) |
| P2 | Caps hold under concurrency | yes | `TestF10...` (1) |
| **P0** | **Caps survive a restart** | **NO** | **impossible today — R-1** |
| **P0** | **Caps hold across processes** | **NO** | **impossible today — R-2** |

The last two cannot be tested because the behaviour does not exist. That is the
honest gap, and it is the same one as the production blocker.

---

## What is still not tested

- **Python 3.10 and 3.12.** `pyproject.toml` claims support; only 3.11.15 has
  ever run this code. The CI matrix covers all three but has never executed.
- **Langfuse integration.** Only the `ImportError` fallback path is tested. The
  actual traced path has never run against a real Langfuse. If the `observe`
  signature changed, we would not know.
- **n8n interoperability.** The webhook is tested with hand-built HTTP requests,
  not against real n8n.
- **Property-based tests.** None. The strongest candidate:
  *for any constitution and any action sequence, executed side effects never
  exceed the declared caps.* `hypothesis` would express that well, but it is a
  new dependency and the brief says not to add one casually. Logged as D-8.

---

## Coverage

**UNVERIFIED as a number** — `pytest-cov` is declared in `pyproject.toml` but
not installed in `.venv`, so I have not run it and will not quote a figure I
did not measure. CI enforces `--cov-fail-under=85`; that threshold is unproven
until CI runs.

Coverage was never the problem here. The old suite would have shown high
coverage on `governance_gate.py` while the feature it implements was broken.
