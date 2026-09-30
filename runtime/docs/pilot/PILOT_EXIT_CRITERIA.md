# PILOT EXIT CRITERIA — Kynd Runtime

## Graduation criteria (ALL must hold — measurable, not "all tests pass")

- [ ] Core workflow (propose → govern → approve → send → audit) has run
      reliably across the full Level 0 → Level 1 progression with no
      unexplained behavior.
- [ ] Zero unresolved P0 incidents.
- [ ] Zero unresolved P1 incidents.
- [ ] Governance remained intact throughout: no unauthorized send occurred
      (a send to a non-allowlisted target, a send without a valid approval,
      or a send exceeding the daily cap). This is checked directly against
      the durable audit trail, not from memory or impression.
- [ ] The customer/operator can, unprompted, explain why any given blocked
      action was blocked, using `store.recent_execution()` — i.e. the
      audit trail is genuinely usable by a non-Kynd-developer, not only by
      whoever built the integration.
- [ ] The customer/operator has successfully performed at least one restart
      (planned or accidental) and confirmed the daily cap and audit trail
      were intact afterward — not merely told this works, but observed it.
- [ ] Deployment is repeatable: a second person (not the original
      integrator) could follow PILOT_SETUP.md and get the same result.
- [ ] Measurable customer value exists — a real answer to "what did this
      replace, and was it faster/more reliable," not merely a belief that
      it might be someday.
- [ ] The customer states, in their own words, that they want to keep
      using it past the pilot.

## The pilot does NOT graduate merely because

- All 168+ engineering tests still pass. That is a necessary baseline
  established before the pilot even started (see the prior D-1/D-6/D-11/D-3
  audits) — it says nothing about whether this specific customer's specific
  workflow actually works or is trusted.
- The calendar says the pilot has run for N weeks.
- No incidents occurred simply because volume was too low to surface any
  (5 sends/day for 3 days is not enough evidence either way — see the
  minimum event counts in PILOT_RUNBOOK.md's level descriptions).

## Possible outcomes at pilot review

- **GO** — graduate to Level 2 discussion (see PILOT_RUNBOOK.md), or to a
  second pilot with a different customer/workflow.
- **EXTEND** — insufficient volume/evidence yet; continue at the current
  level with a defined re-check date.
- **NO-GO** — a P0/P1 pattern, a trust failure, or a customer decision that
  the value isn't there. Document why in the final PILOT VERDICT report
  (see the parent mission's Phase 16 template) — a NO-GO with clear reasons
  is a successful pilot outcome, not a failure of this process.
