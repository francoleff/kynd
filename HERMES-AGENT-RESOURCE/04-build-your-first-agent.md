# 4. Build 1: The Research Brief Agent

Thirty minutes . Maybe an hour . No coding .

You're building the Research Brief Agent . It researches a topic , verifies what it finds , and writes a clean brief to a file . Your own real Agent .

The features it uses are verified against the official docs . The project design is ours .

- **Before you start:**
  - Sections 1–3 done . Hermes installed , a provider configured , `hermes` opens cleanly .
  - Web search enabled . Easiest path : `hermes setup --portal` — web search comes with the Tool Gateway .

  Make a folder :

  ```bash
  mkdir -p ~/kynd/research-agent/briefs
  cd ~/kynd/research-agent
  ```

### The files

### File 1 — `AGENTS.md` (in `~/kynd/research-agent/`)

Hermes injects context files like `AGENTS.md` into every conversation in that folder . This file turns plain Hermes into a Research Brief Agent .

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

### File 2 — `SOUL.md` (global personality — one-time)

Lives at `~/.hermes/SOUL.md` — the agent's permanent voice .

```markdown
# SOUL.md

You are Kynd, a sharp, honest, practical research assistant.
- Plain language. No fluff, no hype, no filler.
- You verify before you state. You say "I don't know" when you don't know.
- You write for a reader who wants to DO something with the information.
- Every factual claim is backed by a source or marked unverified.
```

Heads up : this changes your agent's voice everywhere , not just this project . Skip it if you want the default voice . Switch back anytime : delete the file or use `/personality` presets .

### File 3 — `topics.md` (optional)

```markdown
# Topics to track
- AI agent harnesses (what changed this month)
- Small models that can run on a laptop
- Cheap ways to run agents (serverless, VPS)
```

- **First run:**

  ```bash
  cd ~/kynd/research-agent
  hermes
  ```

  Send this exact prompt :

  ```
  Research "AI agent harnesses" — what they are , the main open-source options right now ,
  and what changed in the last month . Follow my AGENTS.md format and save the brief to briefs/ .
  ```

  What should happen :
  1. The agent acknowledges the task and starts searching (if search is available) .
  2. It may ask a clarifying question via the `clarify` tool — answer it .
  3. It writes `briefs/ai-agent-harnesses.md` .
  4. It replies with a short summary of what it did .

  Success looks like :
  - [ ] `briefs/ai-agent-harnesses.md` exists
  - [ ] The file follows the AGENTS.md format (all 7 sections)
  - [ ] Every key fact has a source link
  - [ ] Nothing looks fabricated — spot-check one claim against its link
  - [ ] The agent finished without errors

- **Iterate — this is the whole method:** You don't ask for a perfect brief . You fix what's wrong :

  ```
  The brief is good but too general. Rewrite it with 3 concrete examples of
  harnesses people actually use, and add a comparison table. Keep the same file.
  ```

  Keep iterating until the output is useful . That's the Kynd method : name one task → describe done → iterate 3 times . Each good iteration teaches the agent — and can become a skill (section 5) .

- **Make it repeatable — a skill:** Tell the agent to capture the workflow :

  ```
  This research-brief workflow worked well. Create a skill for it so I can
  reuse it for any topic.
  ```

  Hermes can create skills autonomously after complex tasks — they land in `~/.hermes/skills/` . Once created , trigger it anytime :

  ```
  /research-brief "local LLMs on a laptop"
  ```

  Doesn't auto-create ? The manual path is in section 5 / ASSETS .

- **Make it automatic — cron** (optional , 5 minutes) . In the same chat :

  ```
  /cron add "0 9 * * 1" "Run the research-brief workflow for the topics in topics.md.
  Save each brief to briefs/. Keep my AGENTS.md format. Deliver: local."
  ```

  - `0 9 * * 1` = every Monday at 9:00 AM . Cron syntax works in `/cron add` .
  - Output lands in `~/.hermes/cron/output/` with `deliver: local` .
  - Manage : `/cron list` , `/cron remove <id>` .

  One gotcha : cron jobs run in fresh sessions with no memory — the prompt must be self-contained . That's why the AGENTS.md + skill combo matters .

- **Test it — anytime you change the setup:**
  1. `cd ~/kynd/research-agent && hermes`
  2. Send the research prompt for a NEW topic (e.g. , "vector databases")
  3. Wait for completion (watch the tool calls stream)
  4. Open the brief — check format , sources , no fabrications
  5. If the cron job exists , confirm it's scheduled : `/cron list`

- **The release gate:**
  - [ ] Fresh install instructions (section 2) reproduce cleanly
  - [ ] AGENTS.md is read (ask : "what does my AGENTS.md say ?")
  - [ ] Briefs save to the right folder with the right name
  - [ ] Format matches AGENTS.md exactly
  - [ ] No fabricated sources (spot-check 2+ links)
  - [ ] Unverifiable claims are marked `[UNVERIFIED]`
  - [ ] Skill works from a fresh chat (`/research-brief <topic>`)
  - [ ] Cron job runs and delivers where configured

- **What you have now:**
  - A persistent agent with a defined role and voice
  - A repeatable research workflow (a skill)
  - An optional scheduled automation (cron)
  - The pattern for everything else : context files shape the agent , prompts steer it , skills capture what works

**NEXT →** [5 — PERSONA, IDENTITY & THE STARTER KIT](05-kynd-starter-kit.md) · or jump to [6 — PRACTICAL AGENT BUILDS](06-real-projects.md)
