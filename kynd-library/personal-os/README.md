# Personal OS

Using agents to run your own life and work. Not a company playbook — a way to give your attention back to the things you actually care about. Kynd's values live here: know yourself, harmony, peace, resonance.

The point is not to automate everything. It is to remove the friction that stops you from doing the work that matters.

## What belongs here

- Personal Assistant setups (text your agent from your phone).
- Inbox triage, reminders, daily briefings.
- Memory systems: teaching an agent your preferences and routines.
- Habit and attention loops that survive contact with real life.

## Seed: the Personal Assistant build

The concrete starting point is [Build 3 in the Hermes course §6](../../HERMES-AGENT-RESOURCE/06-real-projects.md):

1. Set up the gateway (`hermes gateway setup`) → Telegram or Discord bot.
2. Secure it (allowlist your user ID; never `GATEWAY_ALLOW_ALL_USERS=true`).
3. Give it memory: your preferences, routines, standing instructions.
4. Schedule daily briefings and reminders via `/cron add` with `deliver: telegram`.

Release gate: "I can text my agent and get a useful reply, and it runs my Monday briefing unattended."

## What to read first

- [Understand AI agents](../foundation/understand-ai-agents.md) — what "memory" and "gateway" mean.
- [Research Brief Agent case study](../case-studies/research-brief-agent.md) — the same context-file pattern, applied to you.

## Wanted (not yet written)

- **The personal memory setup** — what to tell your agent so it actually knows you.
- **Inbox triage SOP** — turn a flooded inbox into a one-line morning brief.
- **A real personal-OS walkthrough** — what one member automated, and the time it gave back.
