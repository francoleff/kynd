# PILOT SCOPE — Kynd Runtime

## What Kynd Runtime actually is (re-stated for pilot clarity)

A Python **library**, not a hosted service. It has no UI, no dashboard, no
standalone process a customer logs into. "Deploying it" means: a developer
embeds `kynd_runtime` inside code the customer already runs (a script, a
cron job, an n8n workflow, a Hermes agent) and writes the real tool handlers
(SMTP call, Stripe call, etc.) themselves — **Kynd ships none of those**.
Every example in `examples/` uses a fake handler that returns a string; none
call a real API. This is not a gap to fix before the pilot — it is what the
product is. The pilot must supply its own real handler(s).

## The narrowest pilot: single-capability, single-channel, notification-only

**Capability:** `send_notification` — one governed action, sending a message
to a **single pre-approved Slack/email address the customer controls**.

**Why this and not something bigger:**
- It is the smallest unit that exercises the entire real pipeline
  (constitution → gate → approval → idempotency → execution → audit) end to
  end, on a real external system, with a real observable result the
  customer can check themselves (an email/Slack message actually arriving).
- It is fully reversible in effect (a message can be ignored) even though
  the send itself cannot be un-sent — there is no way to make "send a
  message" undo-able, so the safety comes from tight allowlisting and low
  volume, not reversibility of the send itself.
- It requires no financial capability, no destructive capability, and no
  broad external API scope — one webhook URL or one SMTP relay to one fixed
  address.

## Explicitly OUT of scope for this pilot

- `charge_card` or any capability that moves money. Not enabled. The
  constitution for this pilot will not declare this capability at all —
  Kynd denies unknown capabilities by construction (`Unknown capability: X`),
  so there is no code path by which the pilot could accidentally invoke it.
- Any `delete_*`, `drop_*`, `purge_*`-named capability, or any capability
  whose `action_type` is `delete`/`destroy`/`drop`/`purge`.
- Multiple recipients, distribution lists, or "send to whoever the AI
  decides." The allowlist is one address, decided by the customer before
  the pilot starts, changeable only by the customer editing the
  constitution file (not by any code path Kynd exposes at runtime).
- Any capability requiring the AI to choose which external system to talk
  to. One channel, one target, fixed in advance.
- Autonomous operation from day one. See PILOT_RUNBOOK.md's level
  progression — the pilot starts at Level 0 (read-only/dry-run) and only
  advances on evidence.

## Actual customer workflow being tested

```
Customer has a recurring task where an AI currently drafts something
(a status update, a summary, a notification) and a human currently
copies/pastes or manually sends it.

START: AI produces a draft message + a proposed send action
  → CONFIGURE: constitution declares send_notification, allowlisted to
                the customer's one pre-approved address, capped at N/day
  → EXECUTE: Kynd's Executor receives the proposed action
  → GOVERN: gate checks hard rules, broker checks the daily cap and the
             allowlist, an approval is required and verified before send
  → COMPLETE: real handler (customer-provided, e.g. smtplib or a Slack
               webhook POST) sends the message
  → AUDIT: durable record in SQLite — capability, allowed/denied/failed,
            approval used, timestamp — queryable after the fact and after
            a restart
```

## What Kynd Runtime WILL do in this pilot

- Evaluate every proposed send against the constitution before anything
  happens.
- Refuse to send to any address other than the one allowlisted address.
- Refuse to exceed the configured daily send cap.
- Require a real, issued, unexpired, single-use approval before a send
  proceeds — a model-invented approval string is rejected.
- Deduplicate retried requests sharing an idempotency key (no double-send).
- Record a durable, restart-surviving audit trail of every attempt, allowed
  or denied.

## What Kynd Runtime WILL NOT do in this pilot

- Decide the content of the message. Kynd does not generate text; whatever
  produces the draft (the customer's own AI/script) is outside Kynd's
  responsibility and outside this pilot's scope to validate.
- Guarantee the message was *read* or *acted on* by the recipient — only
  that the send handler was invoked and returned without raising.
- Guarantee exactly-once delivery at the network level. Kynd guarantees the
  governance decision (send permitted, not duplicated at the Kynd layer) is
  correct; whether the underlying SMTP/webhook call itself is retried by
  the transport is outside Kynd's control. See PILOT_SAFETY.md.
- Operate without a human-issued approval for the first pilot phase (Level
  0/1). See PILOT_RUNBOOK.md.

## What the customer must provide

1. One approved recipient address/channel (email or Slack webhook URL).
2. A real handler function that performs the send (a few lines of code —
   Kynd does not ship one). This is a genuine input the customer or their
   developer must write; it cannot be fabricated by this audit.
3. A decision on daily send volume cap (recommended starting point: 5/day).
4. A person designated to issue approvals during the pilot (see
   PILOT_RUNBOOK.md Level 1).
5. A place to run it: a machine or process the customer controls, with
   write access to one local file (the SQLite governance database).

None of the above exists yet. This document defines what is needed: it does
not assume a customer, environment, or credential that has not been
provided.
