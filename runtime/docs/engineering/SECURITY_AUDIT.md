# SECURITY AUDIT — Kynd Runtime

Performed 2026-08-31. Findings marked CONFIRMED were reproduced by execution.
No vulnerability in this document is speculative or manufactured.

## Scope

A governance library that gates money movement and outbound messaging, plus an
HTTP listener that exposes those capabilities to a workflow tool. The security
question that matters: **can something reach a capability without passing the
constitution, and can the constitution be made to say yes when it means no?**

---

## S-1 — Unauthenticated network listener over money-moving capabilities. P0. FIXED.

**Before:** `KyndWebhookServer` bound `0.0.0.0:5000` by default with no
authentication of any kind — no token, no signature, no allowlist.

Reproduced against a live server:

```
unauthenticated charge: (200, '{"status": "ok", "capability": "charge_card", "result": "CHARGED"}')
side effects fired: 1
```

Anyone able to reach the port could execute any registered capability, subject
only to the constitution's caps. On a laptop on a café network, or any host
without a firewall, that is remote unauthenticated money movement.

**Fixed:**
- A token is mandatory. The server refuses to construct without one
  (`WebhookConfigError`), so there is no unauthenticated mode to fall into.
- Minimum token length 16; supplied via argument or `KYND_WEBHOOK_TOKEN`.
- Compared with `hmac.compare_digest` — a naive `==` leaks the token by timing.
- Default bind is `127.0.0.1`. Binding an off-host interface raises unless the
  caller explicitly passes `allow_public_bind=True`.
- Accepts `Authorization: Bearer` or `X-Kynd-Token`.

Tests: `TestWebhookSecurity::test_unauthenticated_request_is_rejected`,
`test_wrong_token_is_rejected`, `test_server_requires_token`,
`test_server_rejects_public_bind`, `test_server_rejects_short_token`.

**Residual:** the server speaks plain HTTP. The token crosses the wire in
clear. It is bound to loopback by default, which makes that acceptable; any
non-loopback deployment MUST terminate TLS at a reverse proxy. Documented.

---

## S-2 — Internal exception text returned to unauthenticated callers. P1. FIXED.

**Before:** `n8n_connector.py` returned `str(e)` from any handler exception
straight to the HTTP client. Handler exceptions routinely carry connection
strings, file paths, and credentials.

Reproduced (secret value planted by me in a test handler):

```
handler exception -> (500, '{"status": "error", "message": "db conn postgres://user:***@10.0.0.5/prod failed"}')
```

The real string contained the password in clear; it is redacted here.

**Fixed:** internal failures log server-side with full traceback and return an
opaque `"Internal error executing capability"`. Governance denials (403) still
return their reason, which is intentional — that text comes from the operator's
own constitution, not from internals.

Test: `test_internal_error_does_not_leak_exception_text` asserts the planted
secret does not appear in the response body.

---

## S-3 — Unbounded request body. P2. FIXED.

**Before:** `int(self.headers.get("Content-Length", 0))` then
`self.rfile.read(content_length)` — an attacker-declared length read straight
into memory. A 10 MB body was accepted (verified: returned 200).

**Fixed:** 1 MiB cap, rejected with 413 before reading. The oversized body is
then discarded in bounded 64 KiB chunks so the client can actually receive the
413 rather than a connection reset — and the drain itself is capped at 64 MiB
so a lying `Content-Length` cannot pin a worker open.

Test: `test_oversized_body_rejected`.

**Note:** I introduced the connection-reset bug while writing the fix and the
test caught it. Recorded because it is exactly the kind of thing that ships
silently when the test only asserts a status code it never actually received.

---

## S-4 — Model output flowed into comparisons unvalidated. P0. FIXED.

The core AI-security requirement of the brief: model output is untrusted input.

**Before:** `params.get("amount")` went directly into `amount > max_amount`.

```
amount="600"  -> TypeError: '>' not supported between instances of 'str' and 'float'
amount=-9999  -> EXECUTED  (negative charge, i.e. a refund, uncapped)
```

The string case crashed governance instead of denying — and in the webhook that
surfaced as a 500, i.e. an error path, not a denial path. The negative case is
worse: it moved money in a direction no cap covered.

**Fixed:** amounts are validated at both the gate and the broker — must be a
real, finite, non-negative number; `bool` is explicitly excluded (it is an
`int` subclass in Python and would otherwise pass as `1`/`0`). Anything else is
a governance denial with a clear reason, never an exception.

Tests: `TestF6AmountValidation` (5 cases).

---

## S-5 — Fake verification check in shipped code. P0. FIXED.

`n8n_connector.py:71` shipped `verifier.add_check("output_exists", lambda p: True)`
with a `# placeholder` comment. A caller supplying a `verification` block got a
check that always passed — a mock, in production code, inside the module whose
purpose is preventing exactly that.

**Fixed:** removed entirely. A regression test greps the shipped source to
ensure neither `lambda p: True` nor the word `placeholder` returns.

Test: `test_no_fake_verification_check_remains`.

---

## S-6 — Verification failed open on an empty check set. P1. FIXED.

`Verifier().verify({})` returned `passed=True`. A wiring bug that dropped the
checks would silently convert verification into a rubber stamp.

**Fixed:** zero checks is now a failure with an explanatory message.
`Verifier(allow_empty=True)` is the deliberate opt-out.

Tests: `TestF9VerifierFailsClosed`.

---

## S-7 — `subprocess` with `shell=True`. P2. MITIGATED.

`verification.run_command` ran `subprocess.run(cmd, shell=True)` on a
caller-supplied string. Confirmed to execute shell metacharacters.

This is not remotely reachable — nothing in the package routes untrusted input
into it — so it is a footgun rather than a live vulnerability, and I have not
inflated it into one.

**Mitigated:** `shell` now defaults to `False`; a string is `shlex.split` into
an argv list and executed directly. `shell=True` remains available as an
explicit, documented opt-in. Timeouts and OS errors are caught specifically
instead of a bare `except Exception`.

---

## S-8 — Constitution integrity. P1. FIXED.

The constitution is the entire trust anchor. Before this pass, a malformed one
loaded successfully and failed later, mid-enforcement, with an `AttributeError`:

```
{'capabilities': 'send_email'} -> AttributeError: 'str' object has no attribute 'get'
```

Worse, an unrecognised rule type was silently skipped — which reads as "allow".
A single typo could neuter a safety rule with no signal at all.

**Fixed:** full structural validation at load. Unknown rule types are rejected
by name with the list of known types. Rules that can never match (empty match
list) are rejected. Duplicate capability names are rejected — previously the
first silently won, so appending a stricter definition of an existing
capability did nothing. Negative and non-numeric limits are rejected.

The gate additionally denies on unknown rule types at check time, so a
`Constitution` built directly from a dict and mutated afterwards still fails
closed.

Tests: `TestF3UnknownRuleTypesFailClosed`, `TestF13ConstitutionValidation`.

---

## Secrets review

Searched source, tests, examples, docs, and config for keys, tokens, passwords,
and private-key material.

**No secrets found in the repository.** The only matches are the parameter
names `secret_key` / `public_key` in `observability.py` (Langfuse config
plumbing) and the literal string `"test"` in a test. Both are benign.

**Git history:** single commit, `f82e67c`. No secret-bearing history to purge.

**Improved:** `.gitignore` previously did not exclude `.env`, `*.pem`, or
`*.key`. It does now.

**Untracked artifacts removed:** `__pycache__/*.pyc` and `src/kynd_runtime.egg-info/`
were committed to git. Not a secret exposure, but build output in version
control is how stale bytecode ends up shipped and how merges start failing.

---

## Logging review

- No secret is logged by the package.
- **Note, not a finding:** `ExecutionRecord.params` retains the full parameter
  dict, and gate/broker denials log the capability and reason. If a caller
  passes an API key as a tool parameter, it lands in the in-memory execution
  log. That is the caller's choice, but it is now documented in SECURITY.md so
  nobody discovers it by accident.
- The webhook no longer advertises its Python version (`sys_version = ""`),
  removing a free version-fingerprint for an attacker.

---

## AI / agent security posture

The brief requires: `MODEL → STRUCTURED OUTPUT → SCHEMA VALIDATION → BUSINESS
RULE VALIDATION → AUTHORIZATION → OPTIONAL APPROVAL → EXECUTION`, never
`MODEL → EXECUTE`.

Kynd's shape is correct — the model can only propose; the Executor decides.
Mapping, honestly:

| Stage | Status |
|---|---|
| Schema validation | PARTIAL — amounts, targets, and idempotency keys are typed and validated. Arbitrary tool params are NOT schema-checked; the handler owns that. |
| Business rule validation | PRESENT — hard rules + caps, fail-closed |
| Authorization | PRESENT — capability must exist in constitution AND registry |
| Human approval | PRESENT via `require_param: approval_id` scoped to money action types. **The approval_id is not itself verified** — its mere presence satisfies the rule. A model that invents `"approval_id": "abc123"` passes. See D-2; this is the most important remaining AI-safety gap. |
| Execution | Only reached after all of the above |

**Prompt injection:** out of scope for this package — Kynd never sees a prompt.
Its role is to be the layer that holds when the model is successfully injected.
The relevant question is "if the model is fully compromised, what can it do?"
Answer, after this pass: only what the constitution permits, subject to caps
and allowlists, with every attempt audited. Before this pass: also anything
matching a `block_action_type` rule, and any negative-amount transfer.

**Tool authorization:** `ToolRegistry.register` silently overrides an existing
handler (it logs a warning). A compromised code path could swap the real
`send_email` for its own. Not remotely reachable and not a finding — noted as
debt D-7.

---

## Risk classification of capability operations

| Class | Examples | Required controls | Status |
|---|---|---|---|
| READ ONLY | `generate_report` | capability registration | met |
| LOW RISK | `send_slack_message` | + target allowlist, daily cap | met |
| REVERSIBLE | `post_to_discord` | + audit | met |
| HIGH IMPACT | `charge_card`, `send_payment` | + money cap, approval param, idempotency | met (approval unverified — D-2) |
| IRREVERSIBLE | `delete_*`, `drop_*`, `purge_*` | blocked outright | **met only after F-1 fix** |
