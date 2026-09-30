# Kynd Runtime — Hermes Skill

Kynd is a governance layer on top of Hermes Agent. It adds enforceable rules to every tool call.

## What it does

Every tool call goes through: **Constitution → Gate → Broker → Tool → Audit**

- **Constitution** — YAML file defining mission, hard rules, and capability caps
- **Gate** — validates actions against hard rules (block types, require params, money caps)
- **Broker** — enforces per-day call limits, per-request amount limits, target allowlists
- **Audit** — every attempt (allow or deny) is logged

## Quick start

### 1. Create a constitution file

Create `constitution.yaml` in your workspace:

```yaml
name: my-agent
mission: What this agent does

hard_rules:
  - name: no-delete
    type: block_action_type
    action_types: [delete, destroy]

  - name: require-approval
    type: require_param
    param: approval_id
    action_types: [charge_card]

capabilities:
  - name: send_email
    max_amount: 0
    max_calls_per_day: 100
    allowed_targets:
      - team@kynd.io
      - newsletter@kynd.io

  - name: charge_card
    max_amount: 500.00
    max_calls_per_day: 10
```

### 2. Use in a Hermes script

```python
from kynd_runtime import Constitution, Executor, ToolRegistry

# Load constitution
const = Constitution.load("constitution.yaml")

# Register tool handlers
registry = ToolRegistry()
registry.register("send_email", my_email_function)
registry.register("charge_card", my_stripe_function)

# Create executor
executor = Executor(const, registry)

# Execute through governance
result = executor.execute("send_email", {
    "target": "team@kynd.io",
    "subject": "Hello",
    "body": "This is a test.",
})
```

### 3. Handle blocked actions

```python
from kynd_runtime import KyndExecutionError

try:
    result = executor.execute("charge_card", {"amount": 1000})
except KyndExecutionError as e:
    print(f"Blocked: {e}")
    # Action was denied by gate or broker
```

## Constitution reference

### Hard rule types

| Type | What it does | Example |
|---|---|---|
| `block_action_type` | Blocks specific action types | Block `delete` and `destroy` |
| `block_capability` | Blocks specific capabilities | Block `deploy_production` |
| `require_param` | Requires a param (optionally scoped to action types) | Require `approval_id` for money actions |
| `block_param_value` | Blocks specific param values | Block `destination: personal_account` |

### Capability config

| Field | Type | What it does |
|---|---|---|
| `name` | string | Capability identifier |
| `max_amount` | float | Max $ per request |
| `max_calls_per_day` | int | Max calls per day |
| `allowed_targets` | list | If set, only these targets are allowed |

## Audit trail

```python
# Get all audit entries
for entry in executor.audit_log:
    print(f"{entry.capability}: {'ALLOWED' if entry.allowed else 'DENIED'} - {entry.reason}")

# Get execution log with results
for record in executor.execution_log:
    print(f"{record.capability}: {record.result}")
```

## Verification

A task is "done" only when a real check passes — not when the model says so.

```python
from kynd_runtime import Verifier

verifier = Verifier()
verifier.add_check("file_exists", lambda p: Path(p["path"]).exists())
verifier.add_check("test_passes", lambda p: run_command("pytest"))

result = verifier.verify({"path": "/tmp/output.txt"})
if not result.passed:
    print(f"Failed checks: {result.failures}")
```

## Installation

```bash
pip install -e /Users/francoleff/workspace/kynd-runtime
```

## License

MIT
