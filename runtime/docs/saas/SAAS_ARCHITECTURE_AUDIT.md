# SAAS ARCHITECTURE AUDIT — Kynd Runtime → Kynd OS

**Date:** 2026-09-01
**Repo:** `~/workspace/kynd-runtime` (`francoleff/kynd-runtime`, branch `main`, HEAD `788ce0a`)
**Scope:** Phase 0 only. No implementation performed. No runtime file modified.
**Purpose:** Establish what exists, what can be reused, what must be wrapped,
what must be extended, and what must not be touched — before any SaaS code is
written.

---

## 0. HOW THIS DOCUMENT WAS PRODUCED

Every structural claim below comes from reading the source. Every behavioural
claim marked **PROVEN** comes from executing code against the real runtime on
this machine (`/tmp/kynd_audit_probe.py`, output reproduced verbatim in
§4). Claims I could not execute are marked **UNVERIFIED** and say so plainly.

Verified baseline, re-run rather than taken from the README:

```
$ .venv/bin/python -m pytest -q --cov=kynd_runtime
162 passed in 6.24s
TOTAL  1208 stmts  159 miss  87%
```

That matches the documented 162 tests / 87.09% coverage. The state described in
the mission brief is real.

---

## 1. WHAT EXISTS

### 1.1 Package structure

```
src/kynd_runtime/                        1208 statements, 87% covered
├── __init__.py                  47   public API surface (25 exports)
├── domain_types.py              93   NewType semantic boundaries
├── executor.py                 445   THE single governed execution path
├── persistence.py              806   SqliteStore: quota, audit, idempotency, approvals
├── n8n_connector.py            323   loopback HTTP webhook server
├── verification.py             165   post-hoc "did it actually happen" checks
├── observability.py             98   optional Langfuse decorator
├── tool_registry.py             50   capability name -> callable
├── skill.py                     75   Hermes skill metadata
└── control_plane/
    ├── constitution.py         287   YAML/dict loader + strict validation
    ├── governance_gate.py      306   hard rules, money caps, approval validity
    └── broker.py               264   caps: max amount, calls/day, target allowlist
tests/                        2108   162 tests across 8 files
```

### 1.2 The enforcement path, as actually implemented

`Executor.execute()` (executor.py:109-253) is the only place all six stages
run in order. Reading the code, the real sequence is:

| # | Stage | Code | Side effects |
|---|---|---|---|
| 0 | Idempotency claim | `_try_resolve_via_idempotency` | Writes a `pending` row, or returns cached result |
| 1 | Build typed `Action` | `ActionType()` / `CapabilityName()` | None |
| 2 | Gate check | `GovernanceGate.check` | **None — read-only by contract** |
| 3 | Broker check | `Broker.request` | **Consumes daily quota atomically** |
| 4 | Approval consume | `SqliteStore.consume_approval` | One-time atomic claim |
| 5 | Tool dispatch | `ToolRegistry.call` | The real external side effect |
| 6 | Record outcome | `_record` + `store.append_execution` | Durable audit row |

The ordering is deliberate and correct: a denied action never burns quota
(broker returns before incrementing on every other failure path), and a denied
action never burns an approval (stage 4 runs only after 2 and 3 both pass).

### 1.3 Governance vocabulary the runtime actually enforces

`KNOWN_RULE_TYPES` (constitution.py:59) is a closed set of four. A rule of any
other type is rejected **at load**, and the gate independently re-checks and
denies at evaluation time (governance_gate.py:173). Fail-closed twice.

| Rule type | Required key | Matches on |
|---|---|---|
| `block_action_type` | `action_types` (non-empty) | action type **or** capability-name word match |
| `block_capability` | `capabilities` (non-empty) | exact capability name |
| `require_param` | `param` (non-empty str) | optional `action_types` scope; `verify: approval` enables real verification |
| `block_param_value` | `param` + `blocked_values` | exact param value |

Per-capability limits (broker.py:96-180): `max_amount`, `max_calls_per_day`,
`allowed_targets`. Plus top-level `money_caps[capability]`, where the strictest
of the two wins (`effective_max_amount`, constitution.py:149).

**This is the entire governance vocabulary.** The Constitution Builder UI can
express exactly this and nothing more. Anything a UI offers beyond this list is
a second governance language and is forbidden by the mission's rule 13.

### 1.4 The approval mechanism

`SqliteStore.issue_approval` (persistence.py:606) mints `secrets.token_urlsafe(32)`
— 256 bits, unguessable. An approval row is scoped at issue time to:
capability, optional action_type, optional target, optional max_amount, TTL
(default 3600s), max_uses (default 1 — one-time).

`validate_approval` is read-only (used by the gate). `consume_approval` is the
atomic claim: immutable fields re-checked on read, mutable fields
(`revoked` / `expires_at` / `use_count`) re-checked **inside the UPDATE's WHERE
clause**, so two concurrent consumers of a one-time approval cannot both win.

This is a genuinely sound design and the SaaS Approval Center must sit on top of
it unmodified.

### 1.5 CI, already real

`.github/workflows/ci.yml` — 6 jobs: `test` (3.10/3.11/3.12 matrix, incl. a
3× flake-repeat and an 8-real-OS-process quota race), `typecheck` (mypy),
`lint` (ruff), `security` (pip-audit + bandit), `build` (wheel install into a
clean venv + `py.typed` presence check), `examples` (all four demos must run).

This is a better CI pipeline than most funded startups have. **Extend it. Do
not restructure it.**

---

## 2. LOCAL ENVIRONMENT — what I can and cannot build against

Checked, not assumed:

| Dependency | State |
|---|---|
| Node | v24.13.1, pnpm 11.3.0 — fine for Next.js |
| Python | `.venv` = 3.11.15. **System `python3` is 3.9.6 and cannot run this code** |
| PostgreSQL | `/opt/homebrew/bin/postgres` present |
| Docker | **NOT INSTALLED.** `docker compose up` (mission §35) is not achievable as written |
| Stripe CLI | **NOT INSTALLED.** Needed to verify webhooks locally |
| gh CLI | authed as `francoleff` |

Consequence for §35 (one-command local dev): the deliverable will be a
`make dev` / `./dev.sh` driving local Postgres + uvicorn + next dev, not
docker-compose. Honest substitution, documented, not a silent gap.

---

## 3. REUSE / WRAP / EXTEND / DO-NOT-TOUCH

### 3.1 DO NOT TOUCH — the enforcement core

Every file below is load-bearing, adversarially tested, and CI-gated. The SaaS
imports these; it does not edit them.

```
src/kynd_runtime/executor.py                    the one execution path
src/kynd_runtime/control_plane/governance_gate.py
src/kynd_runtime/control_plane/broker.py
src/kynd_runtime/control_plane/constitution.py
src/kynd_runtime/persistence.py                 approvals + idempotency + quota
src/kynd_runtime/domain_types.py
tests/                                          all 162, unchanged
```

Rule for the whole build: **if a SaaS requirement seems to need a change inside
`src/kynd_runtime/`, that is a signal the SaaS layer is doing something wrong.**
Stop and re-derive. The only legitimate exceptions are listed in §3.4.

### 3.2 REUSE AS-IS — no wrapper needed

- `Constitution(dict)` — **PROVEN**: builds from a plain dict, no file needed,
  and rejects an invalid dict at construction with `ConstitutionError`. The
  Constitution Builder compiles Postgres rows → dict → `Constitution`, and
  validation failures surface as UI errors. No file I/O anywhere in the request
  path.
- `SqliteStore.issue_approval` / `consume_approval` — the Approval Center's
  entire cryptographic story. Nothing to add.
- `Executor.execute` — called once per action, unchanged signature.
- `GovernanceGate.check` — **PROVEN side-effect free** (§4, probe 5). This is
  the *only* legal primitive for a "would this be allowed?" preview.
- `ToolRegistry` — per-request registry populated with that workspace's
  connected integrations.

### 3.3 MUST WRAP — runtime primitives that need a SaaS-layer boundary

**W-1. Credential redaction at the params boundary. (Critical.)**
**PROVEN** (§4, probe 3): every key in `params` is serialised verbatim into
`execution_log.params_json`. A Slack bot token passed as a param is written to
durable storage in plaintext. This is correct behaviour for a library — the
runtime is not a secrets manager and never claimed to be — but it makes one
SaaS rule absolute:

> Credentials never enter `params`. The tool handler is a closure created
> per-request that has already resolved and decrypted its own credential. The
> action carries only the capability, target, amount, and business arguments.

A test must assert this, not a comment. See §6, S-2.

**W-2. Per-workspace runtime state.**
Each workspace gets its own SQLite file: `runtime_state/{workspace_id}.db`.
**PROVEN** (§4, probe 2): tenant A exhausting its daily quota leaves tenant B
untouched, and A's approval token presented against B's store is denied
`approval not found`. This is *physical* isolation — the strongest available —
and it requires zero runtime change.

**W-3. `KyndExecutionError` → customer-facing error.**
The exception message is derived from the operator's own constitution and is
safe to show. `ToolNotFoundError` and everything else must become an opaque
error ID. Mission §32.

**W-4. Approval token injection.**
The AI proposes an action *without* `approval_id`. The server, after a human
approves in the UI, issues a runtime approval scoped to
(capability, action_type, target, amount) and injects the token server-side
immediately before `execute()`. **The model never sees, generates, or handles an
approval token.** The runtime already refuses forged tokens; this ensures the
model is never even in a position to try.

### 3.4 MUST EXTEND — small, additive, backward-compatible

These are the only changes I anticipate inside `src/kynd_runtime/`, and each is
additive with a default that preserves current behaviour exactly:

- **E-1 (likely).** A retention/pruning method on `SqliteStore` — this is
  already open as **D-13** in the existing debt register, and multi-tenant SaaS
  is exactly the "real volume data" the register said should justify it.
- **E-2 (possible).** Per-capability idempotency stale-window — already open as
  **D-12**. Only if a real long-running integration lands.

Nothing else. If the list grows, the growth itself is the finding.

### 3.5 DO NOT REUSE for the SaaS

- **`n8n_connector.KyndWebhookServer`.** It is a correct single-tenant loopback
  server with a single shared static token. It has no concept of a workspace, no
  user identity, no per-tenant credential resolution. The SaaS API is FastAPI
  and replaces it for the product path. Leave the module in place — it is a
  shipped library feature with its own users and CI coverage (mission §43).
- **`verification.run_command(shell=True)`.** Never reachable from any SaaS
  request path. A security test must assert that.

---

## 4. PROBE OUTPUT (verbatim, real execution)

```
PROBE 1 — Constitution accepts a plain dict (no file on disk)
  built from dict OK; hard_rules = 2 capabilities = ['send_message']
  invalid dict rejected at construction: ConstitutionError

PROBE 2 — per-workspace store = physical tenant isolation
  A call 1: EXECUTED
  A call 2: EXECUTED
  A call 3: DENIED — Capability 'send_message' exceeded max calls per day (2)
  B call 1: EXECUTED  <- B quota unaffected by A exhausting its own
  B replaying A's approval token: DENIED — Hard rule 'approval-for-send': approval not found
  A calls_today: 2 | B calls_today: 1

PROBE 3 — params are persisted VERBATIM to execution_log
  execution_log rows containing the secret: 1
  => CONFIRMED: anything in params is written to durable storage.
     SaaS rule: credentials must NEVER travel through params.

PROBE 4 — cost of constructing an Executor per request
  Constitution+Registry+SqliteStore+Executor: 0.601 ms/construction
  => per-request construction is ACCEPTABLE

PROBE 5 — gate check is side-effect free; broker request is NOT
  5x gate.check()  -> quota 0 -> 0  (side-effect free: True)
  1x broker.request() -> quota 0 -> 1  (CONSUMES quota)
  => a SaaS 'preview' path may call the gate, NEVER the broker.
```

**Probe 4 decision:** 0.601 ms to construct the full stack. A per-request
construction has no cache-invalidation bug when a customer edits their
constitution mid-session. Build it per-request; revisit only if measurement
says otherwise. Do not build a cache today.

**Probe 5 decision:** the Governance UI's "what can Kynd do / what needs
approval" panels must be rendered from the workspace's stored rules in
Postgres, or from `gate.check()`. Calling `Broker.request()` to preview would
silently consume the customer's daily quota. This is a trap that would have
been easy to walk into.

---

## 5. TARGET ARCHITECTURE

### 5.1 Shape

```
Browser
  │  HTTPS, httpOnly session cookie
  ▼
Next.js (App Router)               ── presentation only, zero governance logic
  │  fetch, credentials: include
  ▼
FastAPI  ─────────────────────────  auth · authz · tenant resolution · validation · rate limit
  │
  ├── Application services         WorkspaceService, IntegrationService, GovernanceService,
  │   (orchestrate, never enforce)  ApprovalService, ExecutionService, AuditService,
  │                                 BillingService, UsageService
  │
  ├── PostgreSQL ────────────────── SaaS control plane. Tenant-scoped, migrated (Alembic).
  │
  └── kynd_runtime (in-process) ─── ENFORCEMENT. Unmodified import.
        └── runtime_state/{workspace_id}.db   per-tenant durable governance state
                │
                ▼
        Integration adapter (Slack / email) — credential decrypted in-closure,
                │                              never in params
                ▼
        External system
```

**Why FastAPI and not Next.js API routes:** the Executor is Python and must be
called in-process. Shelling out to Python per request, or standing up a second
RPC hop, adds a failure mode and a serialisation boundary in front of the
enforcement path for zero benefit. Two deployables (web, api) is the simplest
credible architecture.

### 5.2 Database — the split (ADR-002)

Two stores. This is the single most important architectural decision in the
build, so the reasoning is explicit:

| | SaaS control plane | Runtime enforcement state |
|---|---|---|
| Engine | PostgreSQL | SQLite, one file per workspace |
| Holds | users, workspaces, memberships, integrations, encrypted credentials, governance rules, approval *requests*, proposals, usage, billing | quota counters, approval *tokens*, idempotency claims, audit log, execution log |
| Owned by | SaaS application services | `kynd_runtime.SqliteStore`, untouched |
| Why | multi-tenant relational data, concurrency, migrations, managed backups | the atomicity guarantees are **proven against SQLite's `BEGIN IMMEDIATE` semantics** by 162 tests including an 8-real-process quota race |

Porting the runtime to Postgres would mean rewriting `consume_approval`,
`claim_idempotency`, and `try_increment_call_count` — the three most
safety-critical functions in the codebase — and re-earning every adversarial
test from scratch. That is precisely the "casually rewrite the enforcement core"
the mission forbids in rule 0.

**Stated cost, honestly:** workspace runtime state is host-pinned to a
persistent volume. This rules out a serverless-filesystem deploy for the API and
caps horizontal scaling at one API host until a Postgres-backed store is
written. At the target scale (first paying customers), one host is correct.
The migration path — implement the `ApprovalStore` Protocol (already defined at
governance_gate.py:26, already the decoupling seam) against Postgres — is
documented now so the decision is reversible later, not load-bearing forever.

### 5.3 Authentication (ADR-003, recommended)

FastAPI owns auth. Opaque session tokens, `secrets.token_urlsafe(32)`, SHA-256
hashed at rest, httpOnly + Secure + SameSite=Lax cookie, server-side revocable.
Passwords via `argon2-cffi`. No invented cryptography; no JWT (unrevocable and
unnecessary here).

Rejected: Supabase/Clerk. Each adds a second identity store to keep in sync with
`workspaces`/`memberships`, plus a token-verification hop in front of the
enforcement path, to replace roughly 150 lines of well-understood code. The
runtime already contains a proven issue-token / hash / verify / revoke pattern
(`issue_approval`) to model this on.

### 5.4 Tenancy rule, non-negotiable

`tenant_id` is **never** read from a request body, query string, or header. It
is resolved from `session → user_id → membership → workspace_id`, server-side,
on every request. A single FastAPI dependency (`get_workspace_context`) is the
only place that resolution exists, and every tenant-scoped query takes its
`workspace_id` from that dependency's return value.

---

## 6. SECURITY FINDINGS CARRIED INTO THE BUILD

Findings against the *planned* SaaS layer, derived from the runtime's real
behaviour. None of these are defects in the runtime.

| ID | Finding | Severity | Mitigation |
|---|---|---|---|
| S-1 | Credentials in `params` are written verbatim to `execution_log` — **PROVEN** | **P0 if violated** | Credentials resolved inside the handler closure. Automated test asserts no execution row ever contains a credential. |
| S-2 | Integration API responses may echo secrets, and results are persisted via `_json_safe(result)` | **P0 if violated** | Adapters return an explicit allowlisted summary dict, never the raw provider response. |
| S-3 | A "preview if allowed" endpoint calling `Broker.request()` silently consumes customer quota — **PROVEN** | P1 | Preview uses stored rules / `gate.check()` only. Test asserts quota unchanged across N previews. |
| S-4 | Model-supplied `approval_id` | P0 | Proposals are schema-validated; `approval_id` is a **rejected key** on the proposal boundary and is injected server-side only. |
| S-5 | Cross-tenant approval replay | P0 | Physically impossible via per-workspace DB — **PROVEN**. Test locks it. |
| S-6 | Stripe webhook forgery / replay | P0 | Signature verification + timestamp window + event-id idempotency table. |
| S-7 | Slack OAuth `state` forgery / CSRF on connect | P1 | Signed, single-use, workspace-bound, TTL'd `state`. |
| S-8 | `verification.run_command(shell=True)` reachable from a request | P0 | Not wired into any adapter. Test asserts unreachability. |

---

## 7. WHAT THE RUNTIME DOES *NOT* GIVE US

Stated plainly so no phase assumes otherwise:

1. No users, no workspaces, no roles, no sessions.
2. No credential storage or encryption of any kind.
3. No real integrations. Every handler in `examples/` is a stub.
4. No HTTP API beyond the single-tenant loopback n8n server.
5. No approval *request* lifecycle. It has approval *tokens*. "A human was
   asked, considered, and decided" is entirely absent and is the SaaS layer's
   job.
6. No billing, no usage metering, no entitlements.
7. No AI layer. Nothing proposes actions; a caller does.
8. No retention/pruning — durable tables grow forever (D-13).
9. Single-host only.

Roughly: the runtime is the last 20% of the request path, hardened to 8.4/10.
The other 80% does not exist yet.

---

## 8. PHASED PLAN

Full task-level plan in `docs/saas/SAAS_IMPLEMENTATION_PLAN.md`. Gate summary:

| Phase | Deliverable | Exit gate (must be proven by execution) |
|---|---|---|
| 0 | This audit | ✅ Complete |
| 1 | Postgres + Alembic + FastAPI + auth + workspaces + Next.js shell | Real signup→login→logout→re-login against real Postgres |
| 2 | Memberships, 4 roles, tenant dependency | Cross-tenant test suite: every attempt denied |
| 3 | Runtime adapter + canonical ExecutionService | Rules → Constitution → Executor, blocked action produces zero side effect |
| 4 | Slack integration (OAuth, encrypted creds, real send) | A real message arrives in a real Slack workspace |
| 5 | Constitution Builder UI | UI rules compile to a valid Constitution; invalid config rejected with a readable error |
| 6 | Approval Center | Request → human decision → server-issued token → execute → audit |
| 7 | Execution + audit dashboard | Every state visible, filterable, no secrets |
| 8 | AI proposal layer | Malformed/hostile proposals rejected at the schema boundary |
| 9 | Stripe billing + usage | Real test-mode subscription, webhook verified, entitlement enforced |
| 10 | Security hardening | Adversarial suite (§55) green |
| 11 | Observability + deploy | Deployed, health-checked, backup restored **for real** |
| 12 | E2E customer workflow | The full §54 sequence, no shortcuts |
| 13 | Production readiness audit | `SAAS_PRODUCTION_READINESS.md` with an honest verdict |

**Sequencing rule:** no phase starts while an earlier phase's gate is red.

---

## 9. DECISIONS REQUIRING THE OWNER

Phases 1–3 are unblocked and can start immediately. These block later phases and
are listed here so they are not discovered at the last minute:

1. **Slack vs email as the first integration** (blocks Phase 4). Recommend
   Slack: OAuth gives a genuine connect/revoke/test-connection flow, channels map
   cleanly onto the runtime's existing `allowed_targets`, and delivery is
   instantly visible. Email needs per-customer DNS domain verification, which is
   a hostile first-run step. Requires Franco to create one Slack app.
2. **Stripe account in test mode** (blocks Phase 9).
3. **Deploy target** (blocks Phase 11). Recommend Fly.io for the API — it
   supports the persistent volume that §5.2 requires — with the frontend on
   Vercel and managed Postgres. Railway also works. Vercel *cannot* host the API,
   because of the volume.
4. **Docker** is absent locally; §35 will ship as a shell script unless Franco
   wants Docker Desktop installed.

---

## 10. VERDICT

**The runtime is a sound enforcement core and is safe to build on unmodified.**
Its layering already anticipated this: `store=` is an optional seam, `ApprovalStore`
is a Protocol rather than a concrete import, `Constitution` accepts a dict,
`gate.check()` is contractually side-effect free. None of that was built for a
SaaS, but all of it makes one possible without touching a line of enforcement
code.

The two findings that would have caused real damage if discovered late — that
`params` is persisted verbatim (S-1), and that a "preview" via the broker
silently consumes quota (S-3) — are both **proven by execution** above, before
any code depends on getting them wrong.

**Phase 0 complete. Nothing implemented. No runtime file modified.**
