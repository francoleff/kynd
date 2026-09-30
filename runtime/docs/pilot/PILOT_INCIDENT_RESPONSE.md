# PILOT INCIDENT RESPONSE — Kynd Runtime

## Severity levels

**P0 — Safety/security/customer-impacting catastrophic failure.**
Examples: a message sent to an address NOT on the allowlist; a send that
bypassed the approval requirement; any evidence the daily cap was exceeded;
any evidence of a forged approval being accepted.
**Action:** invoke the kill switch immediately (PILOT_KILL_SWITCH.md
Mechanism 1). Do not wait to diagnose first. Then diagnose with the process
stopped.

**P1 — Serious incorrect behavior requiring immediate intervention.**
Examples: legitimate sends being incorrectly blocked (denial-of-service
against the customer's own workflow); the audit trail missing entries for
attempts that definitely happened; a crash that loses in-flight state in a
way that can't be explained by the documented crash-recovery limits.
**Action:** pause new approvals (stop calling `issue_approval`), keep the
process running so the audit trail keeps recording, diagnose same-day.

**P2 — Meaningful defect with a workaround.**
Examples: an approval's TTL default (1 hour) is inconvenient for the
approver's actual schedule; the audit query is awkward to run manually.
**Action:** document in PILOT_FAILURE_LOG.md, evaluate at the next
scheduled check-in, do not stop the pilot.

**P3 — Minor defect or usability issue.**
Examples: a log message is unclear; a doc typo.
**Action:** backlog. Do not interrupt the pilot.

## During the pilot

- P0/P1 → **stop affected automation** (kill switch or pause approvals).
  Never let pilot momentum override this. A P0 always wins over "but the
  customer is waiting for this notification."
- P2 → document and evaluate at the next check-in; do not silently patch
  around it without recording why.
- P3 → backlog; do not interrupt.

## Diagnosis procedure (works because of the durable audit trail)

1. Stop the process if P0 (see above).
2. Read the full audit trail for the incident window:
   ```python
   for row in store.recent_execution():
       print(row["ts"], row["status"], row["capability"], row["reason"], row["params"])
   ```
3. If an approval is implicated, check its full record:
   ```python
   row = store.get_approval(approval_id)
   print(row)  # capability, max_amount, target, max_uses, use_count,
                # issued_at, expires_at, revoked, last_consumed_at
   ```
4. Cross-reference against `docs/pilot/PILOT_FAILURE_LOG.md` for whether
   this is a known, already-classified issue.
5. If it is new: add an entry to `PILOT_FAILURE_LOG.md` using the required
   fields (date, workflow, expected, actual, severity, root cause, customer
   impact, reproducible, fix required, status) before doing anything else.
   Do not fix first and document later — the mission requires the honest
   record to exist independent of whether a fix follows immediately.

## Who to contact

**UNRESOLVED — requires customer/operator input.** This document cannot
specify a real contact, on-call rotation, or escalation path because no
pilot customer or operator has been identified yet (see PILOT_SETUP.md).
Fill in before the pilot starts:

- Primary operator: _______________
- Backup / escalation: _______________
- Customer's designated contact for a P0/P1: _______________
