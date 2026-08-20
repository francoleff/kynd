# Automating with cron

Once an agent works, the next lever is making it run without you. Cron is the built-in scheduler: natural-language timing, output delivered anywhere. This page is the decide→build→playbook chain for automation.

**Answers:** When should I automate? How do I write a cron job that actually works? What goes wrong?

## Concept: what cron does

`/cron add` schedules a prompt to run later — once, or on a repeating schedule. It is how a build you ran by hand becomes a system that runs itself. Delivery targets: `local` (files in `~/.hermes/cron/output/`), `telegram`, `discord`, `email`, and more.

## Decide: when to automate

Automate a build when:
- You run the same prompt on a schedule anyway (weekly brief, daily digest).
- The output is safe to produce unattended (no risky commands, no money moved).
- The prompt is **self-contained** — because cron runs in a fresh session with no memory.

Do **not** automate:
- A task that needs your judgment on edge cases.
- Anything destructive or external-facing without checkpoints and approvals set.
- A workflow you have not first run successfully by hand.

The [Problem-First Method](./problem-first-method.md) still applies: automate a solved task, not an unsolved one.

## Build: a real scheduled job

From the [Research Brief Agent](../case-studies/research-brief-agent.md):

```
/cron add "0 9 * * 1" "Run the research-brief workflow for the topics in topics.md.
Save each brief to briefs/. Keep my AGENTS.md format. Deliver: local."
```

- `0 9 * * 1` = every Monday at 9:00 AM (standard cron syntax; Hermes also accepts "every 2h").
- `Deliver: local` → files land in `~/.hermes/cron/output/`.
- Manage: `/cron list`, `/cron remove <id>`.

Because the job has no memory, the prompt points at `topics.md` and `AGENTS.md` (the [context files](../foundation/context-files.md)) so it knows what to do and how. That is the whole trick: **the files carry the memory the session lacks.**

## Playbook: the self-contained cron prompt

Every reliable cron prompt has these parts:
1. **The action** — what to run (a skill name, or the full instruction).
2. **The inputs** — files it should read (topics.md, AGENTS.md).
3. **The format** — "keep my AGENTS.md format."
4. **The delivery** — `deliver: local|telegram|discord|email`.
5. **The safety** — implied: no destructive commands, or explicit approval rules.

## Example

The Kynd Content Engine is the opposite pattern worth noting: it is *not* cron-automated, because publishing needs a human. See [that case study](../case-studies/kynd-content-engine.md) — local-only, files written, never posted. Good automation judgment is knowing what to leave manual.

## What goes wrong

- **"It ran but did nothing."** The prompt assumed memory that wasn't there. Make it self-contained — name the files.
- **Output nobody reads.** If `deliver: local` and you never open the folder, the job is wasted. Set delivery to where you'll see it (Telegram/Discord/email).
- **Silent failures.** A cron job that errors produces no chat. Check `/cron list` and the output folder, or add a delivery step that surfaces failures.
- **Automating before it works by hand.** Always run the prompt manually and pass QA (see [QA discipline](qa-discipline.md)) before scheduling.

## Related

- The spine: [Context files](../foundation/context-files.md)
- Decide first: [Should you use an agent?](should-you-use-an-agent.md)
- Real build: [Research Brief Agent](../case-studies/research-brief-agent.md)
- Source: course §3 (Cron) and §7 (Automation prompts)
