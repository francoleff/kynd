# SYSTEM MAP — Kynd Runtime

Generated from reading every source file at commit `f82e67c`. No inference from filenames.

## What this actually is

A **Python library**, not an application. There is no CLI, no daemon, no database, no
migrations, no scheduler, no auth system, no deployment artifact. `pip install -e .` gives
you importable classes. The only long-running process available is
`KyndWebhookServer.serve_forever()`, started manually from user code.

## Runtime

| Item | Value |
|---|---|
| Language | Python, `requires-python = ">=3.10"` |
| Runtime deps | `pyyaml>=6.0` (only) |
| Dev deps | `pytest`, `pytest-cov` |
| Build backend | setuptools, src-layout |
| Entry points | none declared (`[project.scripts]` absent) |
| Packaging | `kynd_runtime` package under `src/` |
| Local venv | `.venv` = Python 3.11.15. System `python3` = **3.9.6**, below the declared floor. |

## Module inventory

| Module | LOC | Responsibility | Notes |
|---|---|---|---|
| `control_plane/constitution.py` | 69 | Load + typed access to YAML constitution | No schema validation |
| `control_plane/governance_gate.py` | 118 | Check an `Action` against hard rules, capability existence, money cap | Pure function of constitution |
| `control_plane/broker.py` | 127 | Capability caps: calls/day, max amount, target allowlist, audit log | In-memory state |
| `control_plane/__init__.py` | 51 | `ControlPlane` facade (gate + broker) | Not used by `Executor`; parallel API |
| `tool_registry.py` | 50 | name → callable dispatch | Silent override on re-register |
| `executor.py` | 164 | The real pipeline: gate → broker → tool → log | Constructs its own gate + broker |
| `verification.py` | 107 | Post-hoc check runner + `run_command` helper | `shell=True` |
| `n8n_connector.py` | 125 | `http.server` webhook → `Executor.execute` | No auth, binds `0.0.0.0` |
| `observability.py` | 90 | Optional Langfuse wrapper | No-op if langfuse missing |
| `skill.py` | 75 | Static metadata dict for Hermes | No behaviour |

## Data flow (as implemented)

```
caller / n8n webhook
      │  capability: str, params: dict
      ▼
Executor.execute
      │  amount = params["amount"]      ← untyped, unvalidated
      │  target = params["target"]
      │  Action(type=capability, capability=capability, ...)   ← see ARCHITECTURE_AUDIT F-1
      ▼
GovernanceGate.check          hard_rules, capability exists, max_amount
      │  deny → KyndExecutionError
      ▼
Broker.request                calls/day, max_amount, allowed_targets
      │  deny → KyndExecutionError
      │  allow → self._call_counts[cap] += 1      ← unsynchronised, in-memory
      ▼
ToolRegistry.call(capability, params)   ← arbitrary user callable, no timeout, no sandbox
      ▼
ExecutionRecord appended to unbounded list
```

**Update (D-3, 2026-09-01):** at the time this document was written there
were two independent paths to the control plane — `Executor` (used
everywhere) and `ControlPlane` (`control_plane/__init__.py`, used only by
`tests/test_control_plane.py`), which did not share state and whose
`execute()` never called the governance gate. `ControlPlane` has since been
deleted; see `TECHNICAL_DEBT.md` D-3 for the investigation and evidence.
`Executor` is now the sole execution path.

## State

| Kind | Where | Durability |
|---|---|---|
| Source of truth for policy | constitution YAML on disk | read once at load, never re-read |
| Daily call counts | `Broker._call_counts` dict | **process memory; lost on restart; never rolls over by date** |
| Audit log | `Broker._audit_log` list | process memory, unbounded |
| Execution log | `Executor._execution_log` list | process memory, unbounded, retains full params |

There is no persistence layer of any kind. Every safety counter dies with the process.

## External integrations

| Integration | Direction | Auth | Failure handling |
|---|---|---|---|
| n8n | inbound HTTP webhook | **none** | exception text returned to caller |
| Langfuse | outbound SDK | env vars | import guarded; network failures unhandled |
| Tool handlers | outbound, user-supplied | n/a | exception propagates after being mislogged |
| `verification.run_command` | outbound subprocess | n/a | `shell=True`, exceptions swallowed → `False` |

## Configuration

Only the constitution YAML. No environment variables are read anywhere except
`observability.configure_langfuse`, which *writes* `LANGFUSE_*` env vars.

## Tests, CI, deployment

- 62 pytest tests in 7 files, all passing, all in-process, zero integration coverage.
- No CI. No `.github/`. No lint, format, or type-check config or tooling installed.
- No deployment artifact, Dockerfile, systemd unit, or process manager config.
- No backup or recovery concept (there is no persistent data to back up).
