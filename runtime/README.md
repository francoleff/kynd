# Kynd Runtime

[![CI](https://github.com/francoleff/kynd-runtime/actions/workflows/ci.yml/badge.svg)](https://github.com/francoleff/kynd-runtime/actions/workflows/ci.yml)

> A governance layer that decides whether an AI agent's proposed action is
> allowed to happen — and stops it in code when it is not.

**Status:** 0.2.0 — hardened, durable, CI-verified. No open P0 blockers.
Read [Limitations](#limitations-read-this) before deploying anything.

## What it actually is

A single Python library, ~1,200 lines, one runtime dependency (`pyyaml`).

It is **not** an operating system, a runtime, an orchestrator, or a service.
Earlier versions of this README claimed a five-phase architecture with agents,
workflows, and a memory layer. Most of that did not exist in code. This README
describes what is actually implemented.

The idea it does implement: **the brain proposes, the control plane decides.**
An LLM can suggest any action it likes. Whether that action executes is decided
by code reading a YAML constitution — never by the model.

```
caller/model proposes
      │
      ▼
  Executor.execute(capability, params, action_type=...)
      │
      ├─ Governance Gate ── hard rules, money caps ──► DENY (raises)
      │
      ├─ Broker ────────── daily caps, allowlists ──► DENY (raises)
      │
      ├─ Tool Registry ─── the real side effect
      │
      └─ Audit ─────────── every attempt: allowed / denied / failed
```

## Install

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q          # 162 passed
```

Requires Python ≥ 3.10. Verified on 3.10, 3.11, and 3.12 in real CI (see
[`docs/engineering/D11_CI_VERIFICATION.md`](docs/engineering/D11_CI_VERIFICATION.md)).
Only macOS (development) and Ubuntu (CI) have been verified; Windows is untested.

## Use

```yaml
# constitution.yaml
name: my-agent
mission: Handle billing and customer email.

hard_rules:
  - name: no-destructive-actions
    type: block_action_type
    action_types: [delete, destroy, drop, purge]

  - name: require-approval-for-money
    type: require_param
    param: approval_id
    action_types: [charge_card]

capabilities:
  - name: send_email
    max_calls_per_day: 100
    allowed_targets: [team@kynd.io]

  - name: charge_card
    max_amount: 500.00
    max_calls_per_day: 10
```

```python
from kynd_runtime import Constitution, Executor, ToolRegistry, KyndExecutionError

registry = ToolRegistry()
registry.register("send_email", my_smtp_handler)
registry.register("charge_card", my_stripe_handler)

executor = Executor(Constitution.load("constitution.yaml"), registry)

try:
    executor.execute("send_email", {"target": "team@kynd.io", "subject": "Hi"})
except KyndExecutionError as e:
    print("blocked:", e)          # governance said no; nothing happened
```

### Constitution reference

**Hard rules** — unknown types are rejected at load, because a safety rule the
gate cannot enforce would silently mean "allow".

| Type | Blocks | Keys |
|---|---|---|
| `block_action_type` | an action kind, matched against the action type *and* words in the capability name | `action_types` |
| `block_capability` | named capabilities outright | `capabilities` |
| `require_param` | actions missing a param | `param`, optional `action_types` scope |
| `block_param_value` | a param holding a forbidden value | `param`, `blocked_values` |

`block_action_type: [delete]` stops `delete_all_customers`, `soft_delete`, and
`delete-records` — matching on `_`/`-` word boundaries, so `undeletable_archive`
is unaffected. Pass `action_type=` to `execute()` for capabilities whose names
do not carry the verb.

**Capabilities**

| Key | Meaning |
|---|---|
| `max_amount` | Per-request spend ceiling |
| `max_calls_per_day` | Calls per **UTC day**; rolls over automatically |
| `allowed_targets` | Allowlist for `params["target"]`; a missing target is denied |

**`money_caps`** — an alternative per-capability spend ceiling. When both it and
`max_amount` are set, **the stricter one wins**.

### Idempotency

```python
executor.execute("charge_card", {"amount": 100, "idempotency_key": "order-7"})
executor.execute("charge_card", {"amount": 100, "idempotency_key": "order-7"})
# handler ran once; quota consumed once; same result returned
```

Failures are deliberately not cached, so a transient error stays retryable.
The cache is in memory and does not survive a restart.

### Audit

```python
for r in executor.execution_log:
    print(r.status, r.capability, r.reason)   # allowed | denied | failed
```

`allowed` means *governance permitted it*. `status` tells you whether it
actually happened — a failed side effect is never recorded as a success.

### n8n webhook

Authentication is mandatory; there is no unauthenticated mode.

```bash
export KYND_WEBHOOK_TOKEN="$(python -m secrets token_urlsafe 32)"
```

```python
from kynd_runtime import KyndWebhookServer
KyndWebhookServer(executor).start()   # 127.0.0.1:5000
```

```bash
curl -X POST http://127.0.0.1:5000/webhook/send_email \
  -H "Authorization: Bearer $KYND_WEBHOOK_TOKEN" \
  -d '{"params": {"target": "team@kynd.io"}, "idempotency_key": "run-1"}'
```

`200` executed · `401` bad token · `403` governance denial, including a
capability absent from the constitution · `404` capability is in the
constitution but has no registered handler · `413` body over 1 MiB · `500`
handler raised (details logged server-side only).

Binds loopback by default. Binding a public interface requires
`allow_public_bind=True` and should sit behind a TLS-terminating proxy.

## Durable governance (multi-process, restart-safe)

By default, caps/audit/idempotency live in process memory — fine for a single
process, gone on restart (see Limitations). To make them durable and shared
across processes, pass a `store`:

```python
from kynd_runtime import SqliteStore

store = SqliteStore("kynd.db")  # WAL mode, safe from multiple processes
executor = Executor(Constitution.load("constitution.yaml"), registry, store=store)
```

Everything else about `executor.execute(...)` is unchanged. With a store:

- `max_calls_per_day` counts survive a restart and are shared by every process
  pointed at the same DB file — the increment is one atomic SQLite transaction,
  so two processes racing for the last unit of quota cannot both win.
- `idempotency_key` claims are cross-process: a concurrent duplicate request
  blocks behind the DB write lock and returns the first attempt's real result,
  never re-running the handler.
- Approvals (below) are durable and atomically consumed.

### Real approval verification

`require_param` alone only checks that a param is *present* — a model can
satisfy it by inventing a string. Add `verify: approval` to require a real,
issued approval:

```yaml
hard_rules:
  - name: require-approval-for-money
    type: require_param
    param: approval_id
    verify: approval           # <-- makes presence insufficient
    action_types: [charge_card]
```

```python
# Issued by whatever real approval flow you have (Slack button, admin UI...):
approval_id = store.issue_approval(
    capability="charge_card",
    max_amount=500.0,      # this approval's own spend ceiling
    max_uses=1,             # default: one-time use
    ttl_seconds=3600,       # default: expires in 1 hour
)

executor.execute("charge_card", {"amount": 100, "approval_id": approval_id})
```

Rejected: an unissued/forged id, an expired or revoked approval, an approval
issued for a different capability/target, an amount over the approval's own
cap, and reuse of an already-consumed one-time approval. **Without a `store`
configured, `verify: approval` fails closed** — a present `approval_id` is
never silently treated as valid.

See `examples/durable_governance_demo.py` and
[`docs/engineering/D1_IMPLEMENTATION.md`](docs/engineering/D1_IMPLEMENTATION.md)
for the full model, including what crash recovery does and does not guarantee.

## Limitations — read this

**Without a `store`:** caps, audit log, and idempotency keys live in process
memory. A restart resets every daily cap to zero and erases the audit trail.
Two workers means two independent quotas.

**With a `store` (`SqliteStore`):** the above is fixed — see "Durable
governance" above. What is still true even with a store:

- Exactly-once execution of the external side effect itself is not
  guaranteed. If a process dies between "handler ran" and "result recorded,"
  a retry may re-invoke the handler. See `D1_IMPLEMENTATION.md`'s Crash
  Recovery Model for the precise, honest statement of this boundary.
- SQLite assumes local-disk locking semantics — do not put the DB file on
  NFS. This is single-host coordination, not multi-host.

**Unverified:** Langfuse tracing and n8n interoperability against real
instances. CI is verified (see D11_CI_VERIFICATION.md) but Windows is not
tested — only macOS (development) and Ubuntu (CI).

These are tracked as P2 items in
[`docs/engineering/TECHNICAL_DEBT.md`](docs/engineering/TECHNICAL_DEBT.md).

## Engineering docs

A full audit lives in [`docs/engineering/`](docs/engineering/). Start with
[`ARCHITECTURE_AUDIT.md`](docs/engineering/ARCHITECTURE_AUDIT.md) — it documents
13 confirmed defects found in the previous version, including a hard rule that
never fired, and how each was reproduced and fixed.

| Doc | Contents |
|---|---|
| `SYSTEM_MAP.md` | What exists, module by module |
| `ARCHITECTURE_AUDIT.md` | 13 findings with reproduction output |
| `PRODUCTION_READINESS.md` | Baseline, current state, blockers |
| `SECURITY_AUDIT.md` | 8 findings, secrets review, AI-safety posture |
| `RELIABILITY_AUDIT.md` | Failure modes, what survives a restart |
| `TESTING_AUDIT.md` | Why 62 green tests missed 13 bugs |
| `PERFORMANCE_AUDIT.md` | Measured throughput; why nothing was optimised |
| `TECHNICAL_DEBT.md` | Ranked register + readiness score |
| `RELEASE_PLAN.md` | Deployment, env vars, recovery |
| `D1_IMPLEMENTATION.md` | Durable state + real approvals: what closed D-1/D-2, how it was proven |
| `D11_CI_VERIFICATION.md` | CI: 4 real GitHub Actions run IDs, deliberate-failure proof, what closed D-11 |

## Development

```bash
pytest -q                              # 168 tests
python examples/hardening_demo.py      # each F-1..F-13 defect being blocked
python examples/durable_governance_demo.py   # restart-proof caps + real approvals
```

Every fixed defect has a regression test in `tests/test_regressions_hardening.py`.
D-1/D-2 (durable state, real approvals) have their own adversarial suite in
`tests/test_persistence_d1.py` — 41 tests covering restart persistence, real
multi-process concurrency, forged/expired/reused approvals, and crash recovery.

## License

MIT — see [LICENSE](LICENSE).
