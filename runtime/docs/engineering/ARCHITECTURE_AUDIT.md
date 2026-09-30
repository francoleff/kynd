# ARCHITECTURE AUDIT — Kynd Runtime

Every finding below was reproduced by running code, not by reading it. Reproduction steps
are given so anyone can re-verify.

---

## F-1 (P0) — The governance gate is fed the wrong `action.type`, so `block_action_type` never fires

**Reproduced.** Constitution with `hard_rules: [{type: block_action_type, action_types: [delete, destroy]}]`,
capability `delete_all_customers` registered. `executor.execute("delete_all_customers", {...})`
returns `"delete_all_customers:EXECUTED"`. The side effect ran.

**Root cause.** `executor.py:62-67`:

```python
action = Action(type=capability, capability=capability, params=params, amount=amount)
```

`Action.type` is hardcoded to the capability name. `GovernanceGate._check_hard_rule` then
compares `action.type in rule["action_types"]` — an exact string match. So
`block_action_type: [delete]` only blocks a capability *literally named* `delete`.

The gate itself is correct: calling `gate.check(Action(type="delete", capability="delete_all_customers"))`
directly returns `allowed=False`. The Executor never produces such an action.

**Why the tests missed it.** `test_gate_blocks_bad_action` executes capability `"delete"`,
which matches the rule by name coincidence *and* is unregistered, so it would have been
denied anyway. The test passes without the rule doing any work.

**Impact.** The product's headline safety guarantee — "never violate a hard rule" — does
not hold for any capability whose name is not identical to a blocked action type. This is
the single most dangerous defect in the repository.

**Fix.** Actions must carry a declared `type` distinct from the capability. Capabilities
declare their action type in the constitution; the Executor reads it. Unknown/undeclared
types must fail closed, not default to the capability name.

---

## F-2 (P0) — `money_caps` is documented, loaded, and never consulted

**Reproduced.** Constitution with `money_caps: {charge_card: 100}` and capability
`charge_card` with no `max_amount`. `execute("charge_card", {"amount": 999999})` succeeds.

`Constitution.money_caps` and `get_money_cap()` exist. `grep` shows **zero** call sites
outside the constitution module and its own unit test. The gate reads only
`cap_config["max_amount"]`. Any operator who configures spend limits via `money_caps` —
the field named after the concept, and the one the docstring calls "Spend caps per
capability (USD)" — gets no enforcement whatsoever and no warning.

**Fix.** Either enforce it in the gate as a second cap (min of both wins) or delete it and
the accessor. Silent dead safety config is worse than no config. Chosen: enforce, since
removing a documented safety knob is the more surprising change.

---

## F-3 (P0) — Unknown / misspelled hard-rule types are silently ignored

**Reproduced.** `{"name": "no-delete", "type": "block_action_typo", ...}` → action executes,
no error, no warning, no log line. `_check_hard_rule` falls through every `elif` and
returns `None`, which the caller reads as "no violation".

A one-character typo in a constitution silently disables a safety rule. There is no schema
validation on load, so the mistake surfaces only as a security incident.

**Fix.** Validate rule types at constitution load; unknown type = `ConstitutionError`.
Fail closed at the earliest possible point.

---

## F-4 (P0) — Caps are per-process, not per-day

**Reproduced.** `max_calls_per_day: 2` on `charge_card`. Two calls succeed, third denied.
Construct a new `Executor` (== restart the process) and the third call succeeds.

`Broker._call_counts` is an in-memory dict. Introspection confirms no date field exists:
attributes are `_constitution`, `_audit_log`, `_call_counts`. `reset_daily_counts()` is
manual and nothing calls it. So "max calls per day" is really "max calls per process
lifetime", and a crash-loop or a per-request process model gives unlimited spend.

**Fix (documented, not fully implemented — see RELEASE_PLAN).** Correct fix is a durable
counter store keyed by `(capability, UTC date)`. Interim fix landed: date-aware in-memory
counters that actually roll over, plus an explicit, loud statement in the docs that
counters are volatile and a single-process deployment is required until persistence lands.

---

## F-5 (P1) — `Broker._call_counts` mutation is unsynchronised

Check-then-increment at `broker.py:63-93` is not atomic. Two threads can both read
`current_calls = 1` against `max_calls = 2`... the classic TOCTOU.

**Honest status: NOT REPRODUCED under contention.** Twenty threads against `max_calls=1`
produced exactly one execution across five attempts, and a barrier-synchronised variant
did the same. The GIL plus the tiny window makes it very hard to hit in CPython. The race
is real by inspection and becomes trivially exploitable the moment the window widens (a
persistent store, a network call, or a free-threaded build). Treating "I could not trigger
it" as "it is safe" is exactly the reasoning that produces incidents.

**Fix.** A `threading.Lock` around the whole check-and-increment. Near-zero cost, removes
the class of bug.

---

## F-6 (P1) — Failed executions are recorded as `allowed=True` and the audit says they succeeded

**Reproduced.** Handler raises `RuntimeError("smtp down")`. Result: broker call count = 1,
audit log's last entry has `allowed=True`, execution record has `allowed=True` with
`reason="Tool execution failed: smtp down"`.

Two problems. The audit log — the artifact a customer would use to answer "did we charge
this card?" — cannot distinguish *permitted* from *executed*. And `allowed` is overloaded:
it means "governance permitted it" in one field and reads as "it worked" to every consumer.

**Fix.** Add an explicit outcome/status to the execution record (`allowed` / `denied` /
`failed`) and keep `allowed` meaning strictly "governance permitted". Regression test
asserts a raising handler produces `status="failed"`.

---

## F-7 (P1) — Model-supplied `amount` is trusted raw

**Reproduced.** `execute("charge_card", {"amount": "600"})` raises an uncaught
`TypeError: '>' not supported between instances of 'str' and 'float'` from inside the cap
comparison. An LLM returning a stringified number crashes the safety check rather than
being denied by it.

`execute("charge_card", {"amount": -50})` **succeeds** — negative amounts pass every cap
(`-50 > 500` is false). Depending on the payment integration, a negative charge is a refund
to an attacker-chosen party.

`float("nan")` also passes: every comparison against NaN is false.

**Fix.** Coerce and validate `amount` at the Executor boundary before any cap logic:
must be a finite, non-negative real number, or the action is denied with a clear reason.

---

## F-8 (P1) — No idempotency anywhere

`execute("send_email", {..., "idempotency_key": "k1"})` twice → two side effects, two
broker calls. The key is accepted and ignored. Any retry (n8n's own retry, a user
double-click, a webhook redelivery) duplicates the action.

**Fix.** Optional `idempotency_key`; when present, a completed record with the same key
short-circuits and returns the prior result without re-invoking the tool. Documented as
process-local until persistence lands.

---

## F-9 (P1) — `Verifier` with zero checks passes

`Verifier().verify_or_raise({})` returns cleanly. `all([]) == True`. A component whose
entire purpose is "the model cannot self-certify" certifies success when it has been
configured with nothing to check. This is fail-open in the fail-closed component.

Worse, `n8n_connector.py:71` registers a literal placeholder:
`verifier.add_check("output_exists", lambda p: True)`. Every webhook that supplies a
`verification` block is "verified" by a function that returns `True` unconditionally.
That is a fake integration shipped in the main package.

**Fix.** `verify` on an empty check set fails with an explicit reason. The n8n placeholder
is removed — the connector must not pretend to verify.

---

## F-10 (P2) — Two parallel control-plane APIs

`ControlPlane` (`control_plane/__init__.py`) and `Executor` both wire gate+broker, hold
separate state, and are exercised by separate tests. `ControlPlane.execute()` consults the
broker but *never* the gate — a caller using that API gets no hard-rule enforcement at all.
Only its own test uses it.

**Not deleted** (rule 10: prove obsolete first). Documented, and its gate-bypassing
`execute` is the more dangerous half. Recommend deprecating in favour of `Executor`.

---

## F-11 (P2) — `ToolRegistry.register` silently overrides

Re-registering a capability replaces the handler with a `logger.warning` that nobody reads.
In a plugin/skill-loading context that is capability hijack. Reproduced: second
registration wins, returns `"HIJACKED"`.

**Fix.** Raise on duplicate registration unless `replace=True` is passed explicitly.

---

## F-12 (P2) — Malformed constitution structures raise raw `AttributeError`

`capabilities: "send_email"` (string instead of list) → `AttributeError: 'str' object has
no attribute 'get'` from deep inside `get_capability`. `capabilities: [null]` → same.
`hard_rules` as a string silently yields no rules.

**Fix.** Structural validation at load with `ConstitutionError` messages naming the field.

---

## F-13 (P2) — Unbounded in-memory logs retaining full payloads

A single call with a 1 MB param blob keeps that blob in `ExecutionRecord.params` for the
process lifetime. A long-running webhook server has an unbounded, PII-retaining memory leak
by design.

**Fix.** Bounded log with a configurable cap (`deque(maxlen=...)`), default 10 000.

---

## Boundaries, coupling, error handling — summary

- **Boundaries:** gate / broker / registry separation is genuinely good. The Executor
  violates it by inventing `action.type` instead of reading declared metadata (F-1).
- **Circular dependencies:** none found.
- **Coupling:** low. `pyyaml` is the only runtime dependency; Langfuse is import-guarded.
  No database, filesystem, or provider coupling to abstract away. No new abstraction is
  warranted.
- **Error boundaries:** the dangerous pattern is *swallowing*. `verification.run_command`
  catches bare `Exception` and returns `False` — a timeout, a missing binary, and a failing
  command are indistinguishable. `Verifier.verify` catches per-check exceptions and logs at
  WARNING. Both hide operational failure as ordinary negative results.
