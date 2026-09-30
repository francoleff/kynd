# PILOT SETUP — Kynd Runtime

## Inputs required from the customer (none fabricated — real, unresolved)

These are genuine blockers to starting the pilot. None can be filled in by
this audit; each needs a real human decision.

1. **Recipient address/channel.** A single email address or Slack incoming
   webhook URL the customer controls and wants notifications sent to.
2. **Approver identity.** The named person who will call
   `store.issue_approval(...)` before each send during Level 1 (see
   PILOT_RUNBOOK.md). Not the AI, not an automated process at this stage.
3. **Send credentials.** SMTP credentials or a Slack webhook URL/token — the
   customer's own, not a shared/dev credential. Kynd Runtime itself has no
   opinion on how the handler sends the message; it only governs whether the
   send is allowed to be attempted.
4. **Where it runs.** A machine or process the customer controls (their own
   server, a VM, a scheduled task) with:
   - Python ≥ 3.10
   - local disk write access for one SQLite file (the governance database)
   - outbound network access to the one send channel (SMTP port or Slack's
     API), nothing broader
5. **Daily volume cap.** A number (recommended starting point: 5/day).

## Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install kynd-runtime   # once published; for the pilot, install from
                            # this repo directly: pip install -e ".[dev]"
```

Environment variables (customer-supplied, never committed to any repo):

| Variable | Purpose | Required |
|---|---|---|
| `KYND_PILOT_CONSTITUTION` | Path to the pilot constitution YAML | Yes |
| `KYND_PILOT_DB` | Path to the SQLite governance database file | Yes |
| (send credential, name depends on channel — e.g. `SMTP_PASSWORD` or `SLACK_WEBHOOK_URL`) | Used only inside the customer-written handler, never passed through Kynd | Yes |

Kynd Runtime itself needs no credentials — it governs; it does not connect
to anything externally by default (the only network-facing piece, the n8n
webhook server, is not used in this pilot; the handler is called in-process).

## Persistent storage

One file: the SQLite database at `KYND_PILOT_DB`. This holds:
- daily send counts (for the cap)
- the audit trail
- idempotency records
- approval records

**This file is the entire durable state of the pilot.** Losing it loses the
audit trail and resets counters — see PILOT_SAFETY.md and
`docs/engineering/D1_IMPLEMENTATION.md`'s Crash Recovery Model for the exact
guarantees. Back it up like you would any small SQLite application database
(a file copy while the process is stopped, or `sqlite3 kynd_pilot.db
".backup backup.db"` while running — SQLite's own online backup, safe under
WAL mode).

## Startup

```python
from kynd_runtime import Constitution, Executor, ToolRegistry, SqliteStore
import os

store = SqliteStore(os.environ["KYND_PILOT_DB"])
registry = ToolRegistry()
registry.register("send_notification", real_send_handler)  # customer writes this
executor = Executor(
    Constitution.load(os.environ["KYND_PILOT_CONSTITUTION"]),
    registry,
    store=store,
)
```

`real_send_handler` is not provided by Kynd. A minimal SMTP example:

```python
import smtplib
from email.message import EmailMessage

def real_send_handler(params: dict) -> str:
    msg = EmailMessage()
    msg["To"] = params["target"]
    msg["From"] = "pilot@customer-domain.example"
    msg["Subject"] = params.get("subject", "Notification")
    msg.set_content(params.get("body", ""))
    with smtplib.SMTP_SSL("smtp.customer-provider.example", 465) as s:
        s.login("pilot@customer-domain.example", os.environ["SMTP_PASSWORD"])
        s.send_message(msg)
    return f"sent to {params['target']}"
```

## Shutdown

Stop the process (Ctrl-C / SIGTERM). Nothing to flush — every write already
went through a committed SQLite transaction before `execute()` returned.

## Recovery after a crash or restart

```python
# Same two lines as startup — the store re-opens the same file, migrations
# are idempotent (no-op if already at the current schema version), and
# every counter/approval/audit record is exactly where it was.
store = SqliteStore(os.environ["KYND_PILOT_DB"])
executor = Executor(Constitution.load(...), registry, store=store)
```

Verified behavior (see `docs/engineering/D1_IMPLEMENTATION.md`): daily send
counts and the full audit trail survive a real process restart, including
counts made moments before the crash.
