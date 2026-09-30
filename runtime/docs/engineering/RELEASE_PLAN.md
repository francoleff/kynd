# RELEASE PLAN — Kynd Runtime

## Deployment model (actual, not aspirational)

Kynd is a **Python library**, not a service. There are two ways it runs:

1. **Embedded (primary).** A caller imports it, registers handlers, and routes
   tool calls through `Executor.execute`. No ports, no processes.
2. **Webhook (optional).** `KyndWebhookServer` runs a loopback HTTP listener so
   n8n can reach governed capabilities.

### Requirements

| Item | Value |
|---|---|
| Runtime | CPython ≥ 3.10 (**only 3.11.15 verified**) |
| Dependencies | `pyyaml>=6.0` |
| Optional | `langfuse` (tracing, **unverified**) |
| Database | none (this is a blocker, not a feature — see D-1) |
| Persistent storage | none |
| Ports | none embedded; one loopback port if the webhook is used |
| Processes | **exactly one** (see constraint below) |
| Schedulers / workers | none |

### The single-process constraint

**Run exactly one Kynd process.** Caps, audit log, and idempotency keys are
per-process. Two workers means two independent quotas: `max_calls_per_day: 10`
becomes 10 × N.

This is not a tuning preference. It is a correctness boundary until D-1 lands.
Do not put the webhook behind a forking server, a process manager with
`workers > 1`, or a horizontal autoscaler.

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `KYND_WEBHOOK_TOKEN` | yes, if the webhook is used | Shared secret. ≥16 chars. `python -m secrets token_urlsafe 32` |
| `LANGFUSE_PUBLIC_KEY` | no | Tracing |
| `LANGFUSE_SECRET_KEY` | no | Tracing |
| `LANGFUSE_HOST` | no | Tracing |

No other configuration exists. The constitution YAML path is passed in code.

### Secrets handling

- The webhook token is the only secret Kynd itself owns. Keep it out of the
  repo — `.gitignore` now excludes `.env`, `*.pem`, `*.key`.
- Tool handler credentials (SMTP, Stripe, etc.) belong to the caller. **Do not
  pass them as capability params** — `ExecutionRecord` retains the full params
  dict in memory.

## Clean installation, verified

Run from a clean clone:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -q                          # expect: 127 passed
python examples/e2e_demo.py        # expect: exit 0
python examples/hardening_demo.py  # expect: exit 0, all denials shown
```

**Verified 2026-08-31** on macOS/ARM with CPython 3.11.15: `127 passed in
4.18s`, all three example scripts exit 0.

**UNVERIFIED:** installation on Linux, on Python 3.10, and on 3.12. The system
`python3` on the development machine is 3.9.6 and cannot run this package —
anyone following these steps must use an interpreter ≥3.10 explicitly.

## Startup and shutdown

Embedded: object construction. `Constitution.load` raises `ConstitutionError`
on any structural problem — **fail fast at startup rather than mid-action.**
Treat a constitution error as a boot failure; do not catch and continue.

Webhook:

```python
server = KyndWebhookServer(executor, token=os.environ["KYND_WEBHOOK_TOKEN"])
server.start()             # blocks; SIGINT stops it cleanly
# or
server.start_background()  # returns once listening
server.stop()              # shuts down and closes the socket
```

`stop()` releases the socket and joins the thread, so restarts do not leak
descriptors or hit "address already in use".

## Health check

`GET /health` → `{"status": "ok"}`. Unauthenticated by design (a liveness probe
should not need a credential) and reveals nothing about configuration.

There is no readiness endpoint — with no external dependencies, live means ready.

## Backup and disaster recovery

**State that cannot be afforded to be lost:**

| Data | Where | Backed up? | Restorable? |
|---|---|---|---|
| Constitution | YAML in git | **yes, via git** | yes |
| Audit log | process memory | **NO** | **NO** |
| Daily call counts | process memory | **NO** | **NO** |
| Idempotency keys | process memory | **NO** | **NO** |

**There is no backup procedure, because there is nothing durable to back up.**

Writing a fake runbook here would be exactly the fabrication the brief forbids.
The honest statement: recovery from a crash means the audit trail for that
period is gone and all caps reset to zero.

The only real recovery asset is the constitution, which is version-controlled.
To restore governance after a total loss: redeploy, load the same constitution,
accept that historical audit data is unrecoverable.

**This is resolved by D-1 and by nothing else.** A restore procedure will be
written when there is something to restore.

Interim mitigation for anyone running this today: have the caller ship each
`ExecutionRecord` to durable storage as it is produced, rather than relying on
`executor.execution_log`.

## Rollback

Library: pin the previous version. No schema, no migration, so rollback is
purely a dependency change.

**One-way compatibility note:** constitutions are now validated strictly. A
constitution accepted by 0.1.0 may be *rejected* by the hardened version if it
contains an unknown rule type, a duplicate capability, or a negative limit.
That is intentional — those constitutions were silently broken — but it means
an upgrade can fail at boot. Load your constitution against the new version
before deploying.

## Release checklist

- [ ] `pytest -q` green locally
- [ ] CI green on GitHub (**never yet achieved — D-11**)
- [ ] Examples exit 0
- [ ] Existing constitutions load against the new validator
- [ ] Version bumped in `pyproject.toml`
- [ ] CHANGELOG entry stating any newly rejected constitution shapes
- [ ] Confirm the deployment is still single-process

## Release phases

**0.2.0 — the current pass.** Governance correctness, webhook auth, validation,
idempotency, bounded logs, 127 tests, honest docs. Suitable for internal use by
someone who understands the single-process constraint. **Not suitable for
paying customers** — no durable audit.

**0.3.0 — production candidate.** D-1 (durable store), D-2 (real approvals),
D-11 (CI green), D-6 (mypy). This is the first version that can be sold.

**0.4.0 — scale.** Shared counter store for multi-process, verified Langfuse
and n8n, Linux + 3.10/3.12 verification.
