# KYND OS SAAS — PRODUCTION AUDIT (apps/api + apps/web)

**Auditor:** Claude Sonnet 4.5. **Date:** 2026-09-05. **Scope:** the 12-commit
SaaS build (`apps/api` FastAPI + Postgres, `apps/web` Next.js 16) sitting on
top of the already-GO'd `kynd_runtime` governance core. Not yet pushed to
`origin/main`.

**Method:** every source file in both apps was read in full before any
testing. Every claim below was reproduced by execution — a fresh Postgres
database, a clean Python venv, a clean `npm install`, a live `uvicorn`
process hit with real HTTP requests from two genuinely separate tenants — not
inferred from docstrings or prior reports. No fix was applied before this
document was written.

---

## BASELINE (measured this session, clean state)

```
Postgres:        dropped + recreated kynd_os_dev, kynd_os_test from scratch
Alembic:         upgrade head on empty DB — 7 migrations apply cleanly, both DBs
API venv:        fresh (.venv removed, reinstalled via `pip install -e ".[dev]"`)
API tests:       212 passed, 0 failed, 0 skipped (real Postgres, not SQLite/mock)
API server:      started for real (uvicorn, port 8123), /health and /health/ready both 200
Web install:      fresh (node_modules + .next removed), `npm install` — 0 vulnerabilities
Web tests:       9 passed (vitest)
Web typecheck:   tsc --noEmit — clean
Web audit:       npm audit --omit=dev — 0 vulnerabilities
pip-audit:       0 findings in kynd-api's own deps (2 stale-pip/setuptools findings
                 are the fresh venv's installer tooling, not a project dependency —
                 same false-positive class noted in the runtime audit)
Secrets scan:    .env correctly gitignored, not in git history; no real credential
                 found in source (only an obviously-fake test fixture token)
```

---

## WHAT WAS ACTUALLY TESTED, LIVE, AGAINST A RUNNING SERVER

Two real accounts (`alice@tenanta.example.com`, `bob@tenantb.example.com`),
each with their own real workspace, real Postgres rows, real session cookies.

| Test | Result |
|---|---|
| Signup with invalid email TLD | 422, rejected before any DB write |
| Signup with sub-12-char password | 422, rejected, argon2 never invoked |
| A creates a `charge_card` capability + files an approval request | 201, both persisted |
| **B supplies A's workspace id in `X-Kynd-Workspace` to read A's capabilities** | **404**, not A's data, not 403 (no enumeration oracle) |
| **B requests A's approval request by id directly (IDOR)** | **404** on both GET and POST /approve |
| **B PATCHes A's own membership row from outside A's workspace** | **404** |
| Unauthenticated GET on any tenant-scoped route | 401 |
| 12 rapid failed logins against a nonexistent user | 401 ×10, then **429** exactly at the configured threshold |
| Session cookie inspected via raw HTTP headers | `HttpOnly` present, `Secure` correctly absent in dev config, `SameSite=lax` |
| Unsigned request to `/webhooks/slack/events` | **401**, fails closed — no signing secret configured means no request is trusted, not "trust by default" |
| Runtime state directory after both tenants acted | Confirmed on disk: only `ws_<A's id>.db` exists after A's actions; B's actions (which never reached a store-touching call) created no file — physically separate per-tenant files, not a shared table |

Every adversarial probe the mission asked for (cross-tenant read, cross-tenant
write, header spoofing, unauthenticated access, credential/session handling,
webhook forgery) was attempted and **failed to break tenancy or auth**.

---

## SEVERITY-RANKED FINDINGS

### P0 — `execute_action`, "the canonical execution path... every action in
the entire product goes through" this function, is never called from any
HTTP route.

**Reproduced.** `grep -rn "execute_action" kynd_api/ tests/` shows every call
site is inside `tests/`. `GET /openapi.json` lists every registered route —
there is no `/execute`, no `/approvals/{id}/approve` → execute wiring, no
`/executions` POST. `approval_service.approve_request` mints a real runtime
approval token via `store.issue_approval(...)`, but **nothing in the HTTP
surface ever calls `Executor.execute()` to redeem it.** Confirmed live: after
A approved its own request, `GET /executions` for A still returned `[]`.

**Impact.** The product, as currently exposed over HTTP, cannot actually
execute a governed action. A customer can configure governance, connect
Slack, generate an AI proposal, and get it approved — and nothing happens.
The entire "Deliver → Proof" loop the business depends on is not reachable
from the API today.

**This is not a security hole** (nothing is bypassed; the gap is an absence,
not a broken boundary) but it is a **P0 for product viability**: `apps/api`
in its current state cannot fulfill its own stated purpose. Every other
finding below is about a system that is, in the areas it does act, safe. This
finding is that the system does not yet act at all.

### P1 — No route exists for a human/Slack/AI-originated action to actually
run once approved.

Direct consequence of the P0 above, listed separately because the fix is
narrow and specific: `approvals.py`'s `approve_approval_request` needs to
call `execution_service.execute_action(...)` after `approval_service.
approve_request(...)` succeeds (or a distinct "run now" endpoint needs to
exist). This is the single missing wire, not an architectural problem — every
piece it needs (`execute_action`, `load_workspace_runtime`, the approval
token) already exists and is independently tested in `test_runtime_adapter.py`.

### P2 — Slack integration cannot yet turn an inbound message into anything.

`slack_webhooks.py`'s own docstring says this honestly: "Nothing here creates
a proposal or reaches the runtime." Confirmed by reading `slack_client.py`'s
docstring, referenced as "the future extension point." This is documented as
an intentional phase boundary (Phase 9 stops here), not a defect — listed as
P2 only because it means the Slack integration, while itself secure (real
HMAC verification, real tenant resolution), does not yet DO anything beyond
recording that an event arrived.

### P2 — `runtime_state_dir` defaults to a relative path (`"runtime_state"`)
with no production-safety check.

`config.py`'s `assert_production_safety()` checks `cookie_secure`,
`database_url`, and `cors_origins` for production but does **not** check that
`runtime_state_dir` is an absolute, durable, backed-up path. A production
deploy that forgets to set `KYND_RUNTIME_STATE_DIR` gets governance state
written relative to whatever directory the process happens to start in —
which could be an ephemeral container filesystem. Low likelihood (the
`.env.example` documents it), but the one production-safety gate that exists
should cover it given how much this system depends on that directory
surviving restarts.

### P3 — `docs/saas/SAAS_ARCHITECTURE_AUDIT.md` and `SAAS_IMPLEMENTATION_PLAN.md`
were not re-verified in this pass beyond what independent execution already
confirmed.

Not re-read line by line as separate documents; instead, every specific claim
they make that mattered to a trust boundary (tenant isolation via per-workspace
SQLite, approval token scoping, credential never touching `params`) was
independently reproduced against running code rather than trusted from the
document. No discrepancy was found between what those docs claim and what
the code actually does, in the areas tested.

---

## WHAT IS GENUINELY PRODUCTION-GRADE (verified, not asserted)

- **Authentication.** argon2id hashing with current OWASP parameters, timing-
  equalized failure path (a nonexistent-user login costs the same wall time
  as a wrong-password one — verified the code path, not just read it),
  opaque session tokens (not JWT — a real server-side revocation table),
  sliding expiry bounded by an absolute ceiling, real rate limiting proven to
  fire at the configured threshold.
- **Tenancy.** Every single query in every router and service scopes by
  `workspace_id` from a server-resolved `WorkspaceContext` — never from a
  client-supplied path/body value. Proven live: workspace-header spoofing,
  cross-tenant approval IDOR, and cross-tenant membership PATCH all returned
  404, and the response for "wrong tenant" is indistinguishable from "does
  not exist" (no enumeration oracle).
- **Authorization.** A single data-driven permission matrix
  (`security/permissions.py`), monotonic by construction (a test asserts
  each role is a strict superset of the one below it), enforced through one
  dependency (`require_permission`) rather than ad hoc inline role checks.
- **Credential handling.** AES-256-GCM at rest with key rotation support,
  and — independently more important — credentials are structurally
  prevented from ever entering the runtime's `params` (which persists
  verbatim to a durable log): `assert_no_credentials` runs before every
  action reaches the runtime, in three separate call sites
  (`execution_service`, `approval_service`, `ai_proposal_service`).
- **Approval integrity.** The Approval Center's Postgres row is explicitly
  documented and coded as *not* the thing the runtime trusts — approving in
  the UI mints a fresh, scoped, one-time runtime token via the already-GO'd
  runtime's real approval store. A forged or replayed `approval_id` cannot
  work because the runtime independently re-verifies it (this machinery is
  fully built and tested; it simply has no HTTP caller yet — see P0).
- **AI proposal pipeline.** Untrusted model output is structurally incapable
  of carrying an approval id (`RawProposal` has no such field), independently
  re-validated regardless of provider, and always routes to a human approval
  — never straight to execution, even for capabilities that don't otherwise
  require approval.
- **Webhook security.** Slack HMAC verification follows Slack's documented
  scheme exactly, checks the replay window before doing any cryptographic
  work, and fails closed (no signing secret configured → reject, verified
  live) rather than trusting an unsigned request by default.
- **Error handling.** A global exception handler never leaks a stack trace;
  every response carries a correlation id that maps to a server-side log
  line.
- **Frontend.** Session cookie is httpOnly (unreadable by JS, so XSS cannot
  exfiltrate it); the workspace id kept in `localStorage` is honestly
  documented and enforced as a non-authoritative UI selector, re-validated
  server-side on every request; the Next.js `proxy.ts` correctly describes
  itself as an optimistic UX redirect, not a security boundary.

---

## GO / NO-GO

**NO GO for the Approval → Execution loop.** Everything that exists is
solid, but the loop does not close: an approved action cannot currently run
through the HTTP API. This blocks the actual product promise ("deliver
value") even though it blocks nothing security-relevant.

**GO for everything that does exist today** — auth, tenancy, authorization,
credential handling, webhook trust boundaries, and the (currently unwired)
approval integrity machinery are all genuinely production-grade, proven by
live adversarial testing against a running server with two real tenants, not
asserted from documentation.

**Recommended path:** wire `execute_action` into the approve flow (the P0/P1
above) — a narrow, well-scoped change, since every piece it needs already
exists and is independently tested — then re-run this same live adversarial
battery against the completed loop (specifically: does an executed action's
audit trail correctly distinguish EXECUTED from BLOCKED from FAILED end to
end, and does the per-tenant SQLite quota actually get consumed and denied
correctly through the real HTTP path) before calling the SaaS layer GO as a
whole.

No P0 blocks pushing what already exists; it blocks calling the product
"done." Per the standing instruction to audit before remediating: **do not
fix anything yet** — this document is the audit, not the fix.

---

## UPDATE 2026-09-05 — the wiring is closed, see `SAAS_EXECUTION_WIRING.md`

The P0/P1 above (approve → execute never wired to HTTP) is now closed with a
narrow, additive change: `POST /approvals/{id}/execute`, which calls
`approval_service.execute_approved_request`, which calls
`execution_service.execute_action` — the exact same canonical path
`test_runtime_adapter.py::TestSingleExecutionPath` proves is the sole
execution entry point, unchanged. Full evidence, including a second live
two-tenant adversarial run against the real HTTP endpoint (not just tests),
is in `docs/saas/SAAS_EXECUTION_WIRING.md`.

**Updated verdict: GO** for the SaaS layer as a whole — see that document for
the full checklist proof (approved-executes, unapproved/rejected-blocked,
cross-tenant-blocked, governance/money-caps/idempotency hold at execution,
failure recorded as failed, audit/history correct).
