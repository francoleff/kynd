# SAAS IMPLEMENTATION PLAN — Kynd OS

Companion to `SAAS_ARCHITECTURE_AUDIT.md`. That document establishes what
exists; this one establishes what gets built, in what order, and what proof
closes each phase.

**Governing rule:** a phase is closed by *executed evidence*, not by code
existing. Every exit gate below names a command or an observable outcome.

---

## REPOSITORY LAYOUT

Additive. Nothing existing moves.

```
kynd-runtime/                     ← repo root, unchanged name (see ADR note)
├── src/kynd_runtime/             ← ENFORCEMENT CORE — do not modify
├── tests/                        ← 162 runtime tests — do not weaken
├── apps/
│   ├── api/                      ← FastAPI (new)
│   │   ├── kynd_api/
│   │   │   ├── main.py
│   │   │   ├── config.py
│   │   │   ├── db.py
│   │   │   ├── models/           ← SQLAlchemy
│   │   │   ├── schemas/          ← Pydantic in/out
│   │   │   ├── deps.py           ← get_current_user, get_workspace_context
│   │   │   ├── security/         ← passwords, sessions, crypto, rate limit
│   │   │   ├── routers/
│   │   │   ├── services/         ← orchestration only, never enforcement
│   │   │   ├── runtime/          ← THE adapter to kynd_runtime
│   │   │   └── integrations/     ← slack/, email/, base.py
│   │   ├── alembic/
│   │   └── tests/                ← SaaS tests, separate from runtime tests
│   └── web/                      ← Next.js App Router (new)
├── runtime_state/                ← per-workspace .db files (gitignored)
└── docs/saas/                    ← this plan, the audit, ADRs, readiness report
```

**Repo naming:** stays `kynd-runtime`. The published Python package
`kynd-runtime` must keep working for existing library users (mission §43).
The SaaS is a monorepo *around* it.

---

## PHASE 1 — SAAS FOUNDATION

**Goal:** a real person can sign up, log in, land in a workspace, log out, and
log back in to find their state intact.

Tasks:
1. Local Postgres database `kynd_os_dev`; `.env.example` committed, `.env` never.
2. SQLAlchemy 2.0 models + Alembic migration `0001_initial`:
   `users`, `workspaces`, `memberships`, `sessions`.
3. `security/passwords.py` — argon2-cffi hash/verify. No custom crypto.
4. `security/sessions.py` — `secrets.token_urlsafe(32)`, SHA-256 stored,
   httpOnly/Secure/SameSite=Lax cookie, server-side revocation, sliding expiry.
5. Routers: `POST /auth/signup`, `/auth/login`, `/auth/logout`, `GET /auth/me`.
   Signup creates user + workspace + OWNER membership in **one transaction**.
6. Rate limit on all auth endpoints (per-IP + per-email).
7. Next.js: signup, login, dashboard shell, middleware-protected routes.
8. `dev.sh` — starts Postgres, runs migrations, boots api + web.

**Exit gate:** signup → login → logout → login again through the real browser
against real Postgres, session persisting across a full API restart. Password
never stored or logged in plaintext (asserted by test, not by inspection).

---

## PHASE 2 — MULTI-TENANCY AND AUTHORIZATION

**Goal:** cross-tenant access is impossible, and proven so.

Tasks:
1. Roles `OWNER / ADMIN / OPERATOR / VIEWER` with an explicit permission matrix
   in one module — permissions are data, not scattered `if` statements.
2. `deps.py::get_workspace_context` — the **only** place a `workspace_id` is
   resolved. Resolution is `session → user → membership`. A client-supplied
   tenant id is never trusted (§5.4 of the audit).
3. `require_permission(...)` dependency on every mutating endpoint.
4. Team management: invite, accept, change role, remove. Last-OWNER removal
   blocked.
5. **`tests/test_tenant_isolation.py`** — two real workspaces, every
   cross-tenant read/write/approve/audit attempt asserted denied.
6. **`tests/test_authorization.py`** — every sensitive endpoint × every role.

**Exit gate:** both suites green, and a deliberate one-line removal of a
`require_permission` guard makes them go red. Authorization proven, not assumed.

---

## PHASE 3 — RUNTIME ADAPTER

**Goal:** the SaaS calls the enforcement core, and the core is the only thing
that decides.

Tasks:
1. `runtime/constitution_compiler.py` — workspace governance rows → dict →
   `Constitution(dict)`. Emits **only** the four rule types the runtime
   enforces (audit §1.3). A rule the runtime cannot enforce cannot be stored.
2. `runtime/store_factory.py` — `runtime_state/{workspace_id}.db`, per-workspace.
3. `runtime/registry_factory.py` — a `ToolRegistry` populated with handler
   closures for that workspace's connected integrations. **Each closure has
   already resolved and decrypted its own credential. No credential enters
   `params`** (audit S-1).
4. `services/execution_service.py` — the single canonical path. Every action in
   the product goes through this one function, with no alternate route to
   `Executor` anywhere in the codebase.
5. Error mapping: `KyndExecutionError` → 403 with the constitution's own reason;
   everything else → opaque error ID (mission §32).

**Exit gate:** an action allowed by workspace rules executes and audits; a
blocked action returns a readable denial, produces **zero** side effect, and
still writes an audit row. Asserted with a handler that records invocations —
if the handler ran, the test fails.

---

## PHASE 4 — FIRST REAL INTEGRATION (SLACK)

**Goal:** a real message arrives in a real Slack workspace, governed.

Tasks:
1. `security/crypto.py` — AES-256-GCM envelope encryption, key from
   `KYND_CREDENTIAL_KEY` env. Key rotation supported via key id column.
2. `integrations/base.py` — the adapter contract: `connect`, `test_connection`,
   `capabilities`, `execute`, `disconnect`.
3. Slack OAuth v2: signed single-use workspace-bound `state` (audit S-7),
   callback, encrypted token storage, channel listing.
4. Capability `send_message`, args `{target: channel, text: str}`. Adapter
   returns an **allowlisted summary** — `{ok, channel, ts}` — never the raw
   Slack response (audit S-2).
5. Disconnect = revoke at Slack + delete ciphertext.
6. `tests/test_credential_security.py` — no API response, log line, or
   execution row ever contains a token. Asserted by scanning real output.

**Exit gate:** connect a real Slack workspace, run a governed `send_message`,
**see the message in Slack**. Then: no credential in any execution row, no
credential in any API response, disconnect removes it. Requires a real Slack
app (owner action).

---

## PHASE 5 — CONSTITUTION BUILDER UI

**Goal:** a non-developer configures governance without touching YAML.

Rules editable: allowed capabilities, blocked capabilities, approval-required
capabilities, max amount, max calls/day, allowed targets. **Exactly the runtime's
vocabulary, nothing more** (mission §13).

Compile → validate → save is transactional: a config the runtime rejects is
never persisted, and the `ConstitutionError` becomes a readable field-level UI
error.

**Exit gate:** configure rules in the browser only; a `send_message` to a
non-allowlisted channel is then denied by the runtime with the customer's own
rule named in the reason.

---

## PHASE 6 — APPROVAL CENTER

**Goal:** real human-in-the-loop.

`approval_requests` table (Postgres) holds the *lifecycle*:
pending → approved/rejected/expired. The runtime's `approvals` table holds the
*token*. On approve: server issues a runtime approval scoped to
(capability, action_type, target, amount), then executes with the token injected
**server-side**. The model never sees a token (audit S-4).

**Exit gate:** propose → appears in Approval Center → approve as an authorised
user → executes → audit shows who approved and when. Then: reject blocks
execution; a VIEWER cannot approve; an expired request cannot be approved; a
forged/replayed `approval_id` from the client is rejected.

---

## PHASE 7 — EXECUTION + AUDIT DASHBOARD

Read models over the runtime's `execution_log` and `audit_log` joined with
Postgres identity data. Every state visible: proposed, blocked, approval
required, approved, rejected, executing, succeeded, failed, deduplicated.
Filter by date, capability, actor, status, integration. Redaction enforced at
the serialiser, not the template.

**Exit gate:** every question in mission §17 answerable from the UI for a real
action. Automated scan of dashboard API responses finds zero credentials.

---

## PHASE 8 — AI PROPOSAL LAYER

Provider-agnostic interface (`AIProvider`), one concrete implementation.
Model output is **untrusted input**: strict Pydantic schema, capability must
exist in the workspace, `approval_id` is a **rejected key**, unknown fields
rejected. Then straight into the Phase 3 execution service.

**Exit gate:** hostile proposals — unknown capability, injected `approval_id`,
another workspace's channel, malformed JSON, prompt-injected instructions — all
rejected at the schema boundary with no runtime invocation.

---

## PHASE 9 — BILLING + USAGE

Stripe test mode. Checkout, customer portal, webhooks with signature + timestamp
+ event-id idempotency (audit S-6). `usage_records` metered on executions.
Entitlement gates *product features*; **it never touches runtime safety**
(mission §21). A billing outage must not weaken governance — asserted by test.

**Exit gate:** real test-mode subscription, real webhook received and verified,
entitlement changes observable. A replayed webhook changes nothing.

---

## PHASE 10 — SECURITY HARDENING

The full §55 adversarial suite as executable tests: fake tenant/workspace/
approval/role/API-key values, cross-tenant everything, duplicate execution,
quota bypass, webhook replay, credential extraction, direct-executor access via
API, malformed proposals. Plus dependency audit and a bandit pass over
`apps/api`.

**Exit gate:** every bypass attempt fails. Each test is proven meaningful by
temporarily removing its guard and watching it go red.

---

## PHASE 11 — OBSERVABILITY + DEPLOYMENT

Structured JSON logs with request/workspace correlation IDs and a secret filter.
Health checks. Deploy: API + volume (Fly.io), web (Vercel), managed Postgres.
Documented backup and **an actually executed restore** (mission §28).

**Exit gate:** deployed and reachable; a backup is restored into a fresh
database and the app runs against it. Restore is performed, not described.

---

## PHASE 12 — END-TO-END CUSTOMER WORKFLOW

The complete mission §54 sequence — fresh account, no DB manipulation, no
developer shortcuts, 22 steps ending at billing state. Recorded step by step
with real output.

---

## PHASE 13 — PRODUCTION READINESS AUDIT

`SAAS_PRODUCTION_READINESS.md`. Honest verdict from the four options. Every
UNVERIFIED item labelled. Every remaining P0/P1/P2 listed. No claim without
executed evidence behind it.

---

## ADRs TO WRITE (only where the decision is real)

| ADR | Decision | Status |
|---|---|---|
| 001 | Monorepo: FastAPI + Next.js around an unmodified runtime | Decided (audit §5.1) |
| 002 | Postgres for SaaS, per-workspace SQLite for runtime state | Decided (audit §5.2) |
| 003 | Own the auth layer; opaque hashed session tokens | Decided (audit §5.3) |
| 004 | Tenant resolution from session only; per-workspace DB isolation | Decided (audit §5.4) |
| 005 | Integration adapter contract + credential-in-closure rule | Phase 4 |
| 006 | Envelope encryption for credentials | Phase 4 |
| 007 | Synchronous execution; no queue until measurement demands one | Phase 3 |
| 008 | Stripe; entitlement never gates runtime safety | Phase 9 |
| 009 | Deployment topology and the persistent-volume constraint | Phase 11 |

---

## STANDING RULES FOR THE BUILD

1. `src/kynd_runtime/` is not modified. Any additive exception is recorded in
   the audit's §3.4 list, and a growing list is itself a finding.
2. All 162 runtime tests stay green in every commit.
3. Credentials never enter `params`, logs, or API responses. Enforced by test.
4. No endpoint reaches `Executor` except through `ExecutionService`.
5. Nothing rendered in the UI is fake. No placeholder buttons, no dead nav.
6. Nothing is reported complete without executed evidence.
