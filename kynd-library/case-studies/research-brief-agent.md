# Case study: the Research Brief Agent

The first build every Kynd member should ship. Source: the [Kynd Hermes Agent course §4](../../HERMES-AGENT-RESOURCE/04-build-your-first-agent.md). This is the real, working version — not a toy.

## What it is

An agent that researches a topic, verifies what it finds, and writes a clean brief to a file. You give it a topic; it returns a sourced brief in a fixed format.

## Why this one first

- No coding.
- Uses only verified features (web search, file write, skills, cron).
- Produces something you will actually use.
- Demonstrates the full [Problem-First Method](../playbooks/problem-first-method.md): name the task, describe "done", iterate three times.

## The setup

Folder:

```bash
mkdir -p ~/kynd/research-agent/briefs
cd ~/kynd/research-agent
```

### File 1 — `AGENTS.md`

This file shapes the agent. Hermes injects it into every conversation in this folder. (Full explanation: [Context files](../foundation/context-files.md).)

```markdown
# Research Brief Agent

## Role
You are a meticulous research assistant. You produce briefs, not essays.

## Working directory
- Briefs are saved to `briefs/` as markdown files.
- Name each file: `briefs/<topic-slug>.md` (e.g., `briefs/ai-agents-2026.md`).

## Research rules
1. Use web search first. If search is unavailable, say so clearly and work
   from whatever material I provide.
2. Never invent facts, quotes, or sources. Only include claims you can
   attribute to a source you actually read.
3. Prefer primary sources: official docs, papers, repositories, announcements.
4. If a claim cannot be verified, mark it `[UNVERIFIED]` in the brief.

## Brief format (every brief, exactly)
# <Topic>
- **Date:** YYYY-MM-DD
- **Sources:** <count> sources used

## Summary
<2–3 sentences>

## Key facts
- <fact 1 — with source link>
- <fact 2 — with source link>

## What it means
<why this matters, 2–3 sentences>

## Open questions
- <what's still unknown>

## Sources
- <title> — <URL>
```

### File 2 — `SOUL.md` (optional, one-time, global)

Sets the agent's permanent voice. Lives at `~/.hermes/SOUL.md`. Skip if you want the default voice.

```markdown
# SOUL.md
You are Kynd, a sharp, honest, practical research assistant.
- Plain language. No fluff, no hype, no filler.
- You verify before you state. You say "I don't know" when you don't know.
- You write for a reader who wants to DO something with the information.
- Every factual claim is backed by a source or marked unverified.
```

### File 3 — `topics.md` (optional)

```markdown
# Topics to track
- AI agent harnesses (what changed this month)
- Small models that can run on a laptop
- Cheap ways to run agents (serverless, VPS)
```

## The first run

```bash
cd ~/kynd/research-agent
hermes
```

Prompt:

```
Research "AI agent harnesses" — what they are, the main open-source options
right now, and what changed in the last month. Follow my AGENTS.md format and
save the brief to briefs/.
```

What should happen: the agent acknowledges, searches, may ask a clarifying question, writes `briefs/ai-agent-harnesses.md`, and replies with a short summary.

## The iterate loop (this is the method)

You do not ask for a perfect brief. You fix what is wrong:

```
The brief is good but too general. Rewrite it with 3 concrete examples of
harnesses people actually use, and add a comparison table. Keep the same file.
```

Keep going until the output is useful. Each good iteration teaches the agent.

## Make it repeatable — a skill

After a successful brief:

```
This research brief workflow worked well. Create a skill for it so I can
reuse it for any topic.
```

Hermes can create skills autonomously after complex tasks (they land in `~/.hermes/skills/`). Trigger anytime:

```
/research-brief "local LLMs on a laptop"
```

See [Building skills](../playbooks/building-skills.md) for the full pattern.

## Make it automatic — cron (optional)

```
/cron add "0 9 * * 1" "Run the research-brief workflow for the topics in topics.md.
Save each brief to briefs/. Keep my AGENTS.md format. Deliver: local."
```

`0 9 * * 1` = every Monday at 9:00 AM. Cron runs in a fresh session with no memory, so the prompt must be self-contained — that is why the AGENTS.md + skill combo matters.

## Release gate (how you know it is done)

- [ ] Fresh install reproduces cleanly
- [ ] `AGENTS.md` is read (ask: "what does my AGENTS.md say?")
- [ ] Briefs save to the right folder with the right name
- [ ] Format matches `AGENTS.md` exactly
- [ ] No fabricated sources (spot-check 2+ links) — see [QA discipline](../playbooks/qa-discipline.md)
- [ ] Unverifiable claims marked `[UNVERIFIED]`
- [ ] Skill works from a fresh chat (`/research-brief <topic>`)
- [ ] Cron job runs and delivers where configured

## What you learned

The pattern for everything else: **context files shape the agent, prompts steer it, skills capture what works.** Take this and expand it into the [Research Agent](../../HERMES-AGENT-RESOURCE/06-real-projects.md), or use the same shape for any task you do repeatedly.
