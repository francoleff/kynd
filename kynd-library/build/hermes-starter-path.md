# Build: your first agent (the Hermes path)

This is the concrete path from zero to a working agent, using the [Kynd Hermes Agent course](../../HERMES-AGENT-RESOURCE/README.md) as the deep reference. The path is short on purpose: install, build one real thing, then expand.

If you have not read [Understand AI agents](../foundation/understand-ai-agents.md) and [Context files](../foundation/context-files.md), do that first. They take ten minutes and make the rest make sense.

## The path

```
1. INSTALL      → get Hermes running (course §2)
2. SETUP        → connect a model provider (course §2)
3. BUILD 1      → the Research Brief Agent (course §4)
4. BUILD 2      → expand it into a Research Agent (course §6)
5. CHOOSE       → pick your next build from the matrix below
```

## Step 1 — Install

One command installs Hermes. One command connects a provider (`hermes setup --portal` opens a browser login and brings web search with it). Full, verified steps are in [course §2: Infrastructure & Setup](../../HERMES-AGENT-RESOURCE/02-installation-setup.md). You need a computer. That is it.

Success looks like: you type `hermes` and a clean agent session opens.

## Step 2 — Setup

Pick a model. The course explains how to switch providers with `hermes model` (Nous Portal, OpenRouter, OpenAI, Anthropic, Google, DeepSeek, or a local model). Start with whatever is cheapest that works. You can change it later.

Understand the harness pieces in [course §3: The Harness](../../HERMES-AGENT-RESOURCE/03-understanding-the-harness.md) — tools, skills, memory, and context files. You only need the parts you use. The context-file habit is covered in [Foundation](../foundation/context-files.md).

## Step 3 — Build 1: the Research Brief Agent

This is the beginner build. It researches a topic, verifies what it finds, and writes a clean brief to a file. No coding. Thirty minutes to an hour.

Walk it end to end in [course §4](../../HERMES-AGENT-RESOURCE/04-build-your-first-agent.md). The working pattern:

- A folder with an `AGENTS.md` that defines the agent's role, research rules, and output format. (See [Context files](../foundation/context-files.md).)
- (Optional) a `SOUL.md` for voice.
- A first prompt that names the topic and points at the format.
- Three iterations to fix what is wrong — this is the [Problem-First Method](../playbooks/problem-first-method.md) in action.
- Turn the working flow into a reusable skill, and optionally a weekly cron job.

See the [Research Brief Agent case study](../case-studies/research-brief-agent.md) for the exact files and the iterate loop.

## Step 4 — Build 2: the Research Agent

Take Build 1 and make it a tool you rely on: a `topics.md` list, on-demand or scheduled runs, a searchable brief archive, unverifiable claims marked instead of invented. Full build in [course §6](../../HERMES-AGENT-RESOURCE/06-real-projects.md).

## Step 5 — Choose your next build

| # | Build | Difficulty | Core features | Status |
|---|-------|-----------|---------------|--------|
| 1 | Research Brief Agent | Easy | AGENTS.md, skill, cron | COMPLETE (§4) |
| 2 | Research Agent | Easy–Med | Skills, cron, web | COMPLETE (§6) |
| 3 | Personal Assistant | Medium | Gateway, memory | Next |
| 4 | Content System | Medium | Skills, batch | Next |
| 5 | Business Operations | Med–Hard | Cron, MCP, checkpoints | Next |
| 6 | Multi-Agent Workflow | Hard | Delegation, kanban | Next |

Pick the one closest to a problem you actually have. That is the whole point of [Problem-First](../playbooks/problem-first-method.md).

## What you have when you finish

- An agent with a defined role and voice.
- A repeatable workflow captured as a skill.
- The pattern for everything else: context files shape the agent, prompts steer it, skills capture what works.

## Next

- Learn the [Content engine](../playbooks/content-engine.md) if you want to publish what you build.
- Browse the [Tool Library](../resources/README.md) when you need a capability.
- Capture it: [QA discipline](../playbooks/qa-discipline.md).
