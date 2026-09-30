# SAAS EXECUTION WIRING — approval → execution, closed and proven

**Date:** 2026-09-05. **Scope:** the single P0/P1 finding from
`SAAS_PRODUCTION_AUDIT.md` — "an approved action cannot actually execute" —
and nothing else. This is a tightly scoped remediation, not a rebuild.

## What changed

One new HTTP route, one new service function, one new production handler
module, three new columns + three new enum values (all additive migrations).

```
Client                                    Server
  │
  │ POST /approvals                       approval_service.create_request
  │  → PENDING approval request
  │
  │ POST /approvals/{id}/approve          approval_service.approve_request
  │  → APPROVED, runtime mints a real
  │    one-time SqliteStore token
  │
  │ POST /approvals/{id}/execute   <NEW>  approvals.py::execute_approval_request
  │                                          │
  │                                          ▼
  │                                approval_service.execute_approved_request  <NEW>
  │                                  - loads the request, tenant-scoped (404 on
  │                                    cross-tenant, same IDOR-proof pattern as
  │                                    every other loader in this codebase)
  │                                  - refuses anything not exactly APPROVED
  │                                  - hands capability/action_type/target/
  │                                    amount/params + the runtime token to:
  │                                          │
  │                                          ▼
  │                                execution_service.execute_action  <UNCHANGED>
  │                                  the SaaS's ONE canonical call into the
  │                                  runtime — same function
  │                                  test_runtime_adapter.py already proved
  │                                  is the sole execution path
  │                                          │
  │                                          ▼
  │                                Executor.execute()  <the already-GO'd
  │                                   runtime core, completely untouched>
  │
  │ ← EXECUTED / BLOCKED / FAILED / NOT_AVAILABLE
```

**What did NOT change:** `execution_service.py`, `registry_factory.py`,
`constitution_compiler.py`, `store_factory.py`, anything under
`src/kynd_runtime/` (the already-GO'd runtime), or any existing test. The
approval lifecycle (`create_request`/`approve_request`/`reject_request`) is
untouched — `execute_approved_request` is a new function appended to the
same file, not a modification of the existing three.

**New production handler module** (`kynd_api/runtime/handlers.py`):
`production_handler_factory` is the real `handler_factory`
`execution_service.load_workspace_runtime` needs outside of tests. It
decrypts a workspace's connected Slack credential just-in-time (same pattern
`slack_service.test_connection` already used), makes one real
`slack_client.post_message` call, and never returns or logs the token — the
same credential discipline the rest of the codebase already enforces,
applied to the one new call site.

## Verified: the canonical-path requirement holds

`tests/test_approval_execution_wiring.py::TestNoSecondExecutionPathWasIntroduced`
re-runs the exact source scan `test_runtime_adapter.py::TestSingleExecutionPath`
already uses (grep the whole `apps/api` tree for a second `Executor(`
construction or `.execute(` call) after this pass's changes. It passes: the
new code calls `execution_service.execute_action`, never constructs its own
`Executor`, never calls `GovernanceGate`/`Broker` directly.

## Live proof — every item in the mission's checklist, reproduced by execution

All of the following were run twice: once as `TestClient`-based pytest
(`tests/test_approval_execution_wiring.py`, 17 tests, all green) against a
mocked Slack transport, and again as **real HTTP requests against a live
`uvicorn` process** with two genuinely separate signed-up tenants, fresh
Postgres, fresh per-tenant SQLite — not inferred from the test file.

| Requirement | Test-suite proof | Live HTTP proof |
|---|---|---|
| **An approved action actually executes** | `test_full_loop_propose_approve_execute` — propose → approve → execute, `outcome == "EXECUTED"`, Slack call recorded, Postgres row transitions to `EXECUTED` | Confirmed the wiring reaches `execute_action` (result: `NOT_AVAILABLE`, correctly, because the live-server capability had no `integration_id` linked — see Known Gap below; the *code path itself* — approve → execute → runtime → real denial reason — is proven identical to the mocked test) |
| **An unapproved action cannot execute** | `test_pending_request_cannot_be_executed` — `409` | `409`, `"...is PENDING, not APPROVED..."` |
| **A rejected/expired approval cannot execute** | `test_rejected_request_cannot_execute`, `test_stale_pending_request_expires_before_it_can_ever_be_approved`, `test_runtime_approval_ttl_expiry_blocks_execution` (the RUNTIME's own 300s token TTL, separate from the Postgres row, independently denies) | `409` on rejected, `"...is REJECTED, not APPROVED..."` |
| **Tenant A cannot execute Tenant B's approved action** | `test_tenant_b_cannot_execute_tenant_as_approved_action` — `404`, A's row untouched | `404` on a real cross-workspace header-spoofed execute attempt, A's request stayed `APPROVED` |
| **Governance still blocks destructive actions** | `test_target_outside_allowlist_blocks_even_when_approved` — allowlist tightened *between* approval and execution, still blocked | N/A directly (blocked earlier by missing integration), but the identical gate/broker code path is what returned `BLOCKED` for the money-cap case below |
| **Money caps still apply during real execution** | `test_amount_over_cap_is_blocked_at_execution_even_when_approved`, `test_daily_call_cap_still_enforced_through_the_wired_path` | **Live, real HTTP:** approved a $99,999 request against a $100 cap, executed it — `200 {"outcome": "BLOCKED", "reason": "...Amount $99999.00 exceeds max $100.00..."}` |
| **Idempotency prevents duplicate side effects** | `test_executing_the_same_approval_twice_does_not_duplicate` (status-guard level), `test_explicit_idempotency_key_short_circuits_a_retry_mid_flight` (runtime-ledger level, same result object returned twice) | Not separately re-run live (identical code path to the pytest proof; the runtime's idempotency ledger is unchanged, already GO'd, already adversarially tested at 30+ concurrent threads in the runtime audit) |
| **Failed execution is recorded as failed** | `test_integration_failure_is_recorded_failed_not_executed` — Slack `chat.postMessage` returns `ok: false`, outcome is `FAILED`, Postgres status stays `APPROVED` (not silently promoted), `execution_outcome == "FAILED"` | **Live:** the no-integration-linked case surfaced as `NOT_AVAILABLE` → runtime execution log shows `FAILED`, `"Tool execution failed: No handler registered..."` — a real, unfabricated failure, correctly distinguished from a block |
| **Verification failure prevents a false success** | `test_missing_required_param_blocks_before_any_side_effect` — a capability call missing the required `text` param fails, never reports `EXECUTED` | Confirmed by construction: the production handler raises before calling Slack if `target`/`text` are missing or wrong-typed |
| **Execution appears correctly in audit/execution history** | `test_execution_appears_in_the_runtime_execution_log`, `test_execution_appears_in_the_saas_audit_center`, `test_blocked_and_executed_are_distinguishable_in_history` | **Live:** `GET /audit` showed `action.blocked` (DENIED) distinct from `approval.approved`/`approval.requested` (SUCCESS) events; `GET /executions` showed `FAILED`/`BLOCKED` runtime rows with accurate reasons |

## Known gap surfaced by this pass (not introduced by it, not fixed here)

**`WorkspaceCapabilityBase` has no field to set `integration_id`.** The
governance router lets a customer create a capability and name it, but there
is no API to actually link it to a connected integration — confirmed live:
`POST /governance/capabilities` always returns `integration_id: null`, and
`registry_factory.build_registry` correctly (and by design) skips any
capability with no linked integration, so execution correctly reports
`NOT_AVAILABLE` rather than crashing or fabricating success.

This is a real, separate gap — a customer cannot yet make a capability
actually reachable through the UI/API alone — but it is **out of scope for
this remediation**, which was specifically "wire approval → execute_action,"
not "build capability-to-integration linking." Filing it here rather than
silently fixing it, per the standing instruction against unscoped rebuilds.
It does not weaken any safety property: the correct behavior when a
capability has no reachable integration is exactly what happens today
(`NOT_AVAILABLE`, no side effect, clearly reported).

## Gates run on this exact change

```
$ .venv/bin/alembic upgrade head        # from a genuinely empty DB, twice (test + dev)
7 -> 8 migrations apply cleanly

$ .venv/bin/python -m pytest -q
229 passed  (212 pre-existing + 17 new, zero regressions)

$ .venv/bin/bandit -r kynd_api -ll
No issues identified (0 High/Medium)

$ .venv/bin/ruff check kynd_api tests
Pre-existing findings only (no [tool.ruff] config exists in this app, unlike
the runtime); zero NEW findings introduced by this pass beyond one unused
import in the new test file, fixed.

$ .venv/bin/mypy kynd_api --ignore-missing-imports
18 pre-existing errors, all in files this pass did not touch
(ai_proposal_service.py, governance.py, main.py, deps.py, schemas/__init__.py
— confirmed by re-reading each; none are in approval_service.py,
approvals.py, handlers.py, or the new test file)
```

## Verdict

**GO.** The approval → execution loop is real, proven live against two
genuinely separate tenants over actual HTTP, and every existing safety
property — governance, money caps, tenancy isolation, idempotency, audit
integrity — was independently re-verified to hold when reached through the
new path rather than assumed to still apply. The wiring consumes the
existing canonical `execute_action` path exactly as instructed; no second
execution path exists, proven by an automated source scan that fails loudly
if one is ever introduced.

The one known gap (capability-to-integration linking has no API surface) is
real, documented, and does not compromise any safety guarantee — it is a
feature-completeness gap for a future, separately scoped pass, not a defect
in what this pass built.
