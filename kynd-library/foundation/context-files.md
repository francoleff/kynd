# Context files

The single most leverage-rich habit in agent building: put instructions in files the agent reads automatically. This page teaches the system every Kynd build sits on.

**Answers:** What are context files? Which one do I use when? How do I write a good one? What goes wrong?

## What a context file is

A markdown file the harness injects into every conversation automatically. You write it once; the agent reads it every time. No pasting the same rules into every prompt. This is how you turn a generic chat bot into "your Research Brief Agent" or "your Content Agent."

## The three layers

| File | Scope | Location | Use it for |
|------|-------|----------|------------|
| `SOUL.md` | Global identity & voice | `~/.hermes/SOUL.md` | Who the agent is, how it talks. One location, always read. |
| `.hermes.md` / `HERMES.md` | Project instructions | Project root | Highest-priority project rules. |
| `AGENTS.md` | Project conventions | Project root | Role, working directory, rules, output format. |
| `CLAUDE.md` / `.cursorrules` | Imported | Project root | Reused from other AI tools you already use. |

The habit that pays the most: **one project, one folder, one `AGENTS.md`.** Every build in the Kynd course follows this. The course's workspace convention:

```
~/kynd/
  research-agent/      → AGENTS.md + briefs/        (Build 1)
  personal-assistant/  → AGENTS.md + gateway setup   (Build 3)
  content-system/      → AGENTS.md + skills/         (Build 4)
```

## How to write a good AGENTS.md

Use the shape from the Kynd starter kit. Five parts:

```markdown
# <Project Name>

## Role
You are <role>. You produce <output type>, not essays.

## Working directory
- <where outputs go, naming convention>

## Rules
1. <rule 1, e.g., "verify claims before stating them">
2. <rule 2, e.g., "never invent sources">
3. <rule 3, e.g., "ask before destructive commands">

## Output format (every deliverable, exactly)
# <Title>
## Summary
## Details
## Sources

## Done looks like
- <checklist of what "finished" means>
```

The **"Done looks like"** checklist is the most important part. It is how you tell the agent what success is — the same move as step 2 of the [Problem-First Method](../playbooks/problem-first-method.md).

## When to use which

- Setting the agent's permanent personality? → `SOUL.md`.
- Rules for one specific project? → `AGENTS.md` in that folder.
- Reusing instructions you already wrote for Claude/Codex? → drop the `CLAUDE.md`/`.cursorrules` in the root; it imports.

## What goes wrong

- **Too vague.** "Be helpful" teaches nothing. Name files, formats, and what "done" means.
- **No "done" definition.** The agent guesses. Always include the checklist.
- **Forgetting cron is amnesic.** A scheduled job runs in a fresh session with no memory. Its prompt must be fully self-contained — the context file is what makes that possible.
- **Secrets in context files.** Context files are readable by the agent and may land in logs. Put keys in `~/.hermes/.env`, never in `AGENTS.md`.

## See it work

The [Research Brief Agent case study](../case-studies/research-brief-agent.md) is a real `AGENTS.md` in action — role, research rules, and a 7-section brief format. The [Kynd Content Engine](../case-studies/kynd-content-engine.md) is what happens when you automate content from the same shape.

## Next

- Build one: [Hermes starter path](../build/hermes-starter-path.md).
- Make it repeatable: [Building skills](../playbooks/building-skills.md).
- Check its output: [QA discipline](../playbooks/qa-discipline.md).
