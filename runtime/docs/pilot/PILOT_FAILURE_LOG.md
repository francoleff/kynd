# PILOT FAILURE LOG — Kynd Runtime

Every unexpected behavior observed during the pilot gets recorded here, in
the order it happens. Do not hide embarrassing failures — the pilot exists
to find them. An empty log after real customer volume is not a sign of
success; it may mean nobody looked.

## Entry template (copy for each new entry)

```
### YYYY-MM-DD — <short title>

DATE:
WORKFLOW:              (what real customer action was in flight)
EXPECTED:              (what should have happened per PILOT_SCOPE.md / PILOT_SAFETY.md)
ACTUAL:                (what actually happened, verified from store.recent_execution())
SEVERITY:              P0 / P1 / P2 / P3 (see PILOT_INCIDENT_RESPONSE.md)
ROOT_CAUSE:            (only fill in after real investigation, not a guess)
CUSTOMER_IMPACT:       (what the customer actually experienced/saw)
REPRODUCIBLE:          yes / no / unknown — if yes, include exact repro steps
FIX_REQUIRED:          yes / no — if yes, link the fix commit once it exists
STATUS:                open / investigating / fixed / accepted-risk
```

## Simulated pre-pilot findings (Phase 8 dry run, 2026-09-01)

These are not real customer incidents — they were found running the
required Phase 8 simulated pilot test suite before any real customer was
involved. Recorded here per the mission's instruction that unexpected
behavior gets logged, including behavior found during pilot preparation.

### 2026-09-01 — Simulated-pilot test-script arithmetic error (not a Kynd defect)

DATE: 2026-09-01
WORKFLOW: Phase 8 simulated pilot, scenario 8 (RECOVERY after restart)
EXPECTED: my test script asserted the daily cap would already be exhausted
  (3/3) immediately after a restart.
ACTUAL: the cap was correctly at 2/3, not 3/3 — my own test's arithmetic
  did not account for idempotency correctly: an earlier duplicate-request
  scenario (step 5) made two `execute()` calls sharing one idempotency key,
  and only the FIRST of those two calls consumes quota (this is Kynd's
  correct, documented, intentional behavior — see D-1's idempotency model).
  My test script's comment assumed both calls consumed quota.
SEVERITY: P3 (test-script bug in the pilot-prep harness, not in Kynd itself)
ROOT_CAUSE: incorrect assumption written into the simulated-pilot test
  script about how many real sends had accumulated by that point in the
  scenario sequence; Kynd's actual behavior (idempotent replay does not
  re-consume quota) is correct and matches its own documentation and the
  D-1 test suite.
CUSTOMER_IMPACT: none — no real customer or pilot was running; this was
  found and fixed during pre-pilot preparation, which is exactly what
  Phase 8 exists to catch.
REPRODUCIBLE: yes — was the original, buggy version of
  `/tmp/simulated_pilot.py`'s scenario 8 (not committed to the repo).
FIX_REQUIRED: yes — fixed by correcting the test script's expected count
  from 3/3 to 2/3-then-3/3, matching Kynd's actual, correct, verified
  idempotency behavior. No Kynd source code change was needed.
STATUS: fixed
```
21 passed, 0 failed (after fix)
```
''')
