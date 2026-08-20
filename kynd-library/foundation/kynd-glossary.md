# Kynd glossary

The words we use, defined once. If a term in the Library is unclear, it should be here. If it is not, that is a gap — tell us in Discord.

## Kynd itself

- **Kynd** — a free community of builders. The name stands for **Know yourself, Kindness, Harmony, Peace, Resonance**. The mission: educate on technology so visionaries can build the life they want. Tagline: *Know yourself, build with intention.*
- **Builder** — anyone making things with technology, at any skill level. You do not need a job title.

## Core methods

- **Problem-First Method** — Kynd's foundational approach: start from one real task you do, write what "done" looks like, then talk to an AI and tell it what you want, iterating three times. Full version: [Problem-First Method](../playbooks/problem-first-method.md).
- **One pillar, four platforms** — Kynd's content system. Write one deep essay (the pillar), then cut it into four platform posts. Detail: [Content engine](../playbooks/content-engine.md).

## Agent vocabulary

- **Agent** — a program that runs a model and gives it tools so it can act, not just answer.
- **Harness** — the program that runs the model and connects it to tools. (See [Understand AI agents](understand-ai-agents.md).)
- **Model** — the LLM "brain" (GPT-4o, Claude, Gemini, etc.). Swappable inside a harness.
- **LLM** — Large Language Model. The text-in, text-out neural network at the core of an agent.
- **Tool / toolset** — a capability the agent can use (web search, file write, code run). Grouped into toolsets (web, terminal, file, browser, memory, delegation, cron).
- **Terminal backend** — where the agent's shell commands run: local (your machine), docker, ssh, or serverless (modal/daytona). Local is fine to start.
- **Memory** — what the agent remembers across sessions. Lives in `~/.hermes/memories/` (MEMORY.md for agent notes, USER.md for your profile, each with a hard character limit) plus a searchable session history. The agent writes memory itself; you tell it what to remember.
- **Context file** — a markdown file auto-injected into every session to shape the agent. See [Context files](../foundation/context-files.md).
- **Skill** — a saved, reusable procedure (`SKILL.md`) an agent can load to do a specific job well. Skills are portable (open `agentskills.io` standard).
- **MCP** — Model Context Protocol. A standard way to connect an agent to external systems (databases, APIs, apps).
- **Subagent** — a smaller agent spawned by a main agent (via `delegate_task`) to do one piece of a bigger job in parallel.
- **Cron** — a schedule. "Run this every Monday at 9am." Cron jobs run in fresh sessions with no memory, so the prompt must be self-contained.
- **Gateway** — one process that connects your agent to 20+ messaging platforms (Telegram, Discord, Slack, WhatsApp, Signal, Email). Protected by allowlists; never `GATEWAY_ALLOW_ALL_USERS=true` on an agent with terminal access.
- **Checkpoints / rollback** — snapshots taken before destructive operations; `/rollback` undoes them. Enable checkpoints in config.
- **Approvals** — the safety gate. `smart` (auto-approve safe, ask on risky) is the default; `manual` asks more; `off` is dangerous.

## Kynd project files

- **SOUL.md** — the agent's global identity and voice (`~/.hermes/SOUL.md`).
- **AGENTS.md** — per-project rules, conventions, and output format (project root).
- **.hermes.md / HERMES.md** — project instructions, highest priority, also in the project root.
- **SKILL.md** — a single reusable skill's definition.
- Templates for all of these ship with the [Hermes starter path](../build/hermes-starter-path.md) and in the course's `ASSETS/`.

## Status words you will see

- **Top 50** — in the [Tool Library](../resources/README.md), a tool we would reach for today.
- **Emerging** — promising but new, unproven, or still changing fast.
