# Building skills

A skill is how your agent learns. Once you have a workflow that works, capture it as a skill and it becomes a one-word command you can run forever. This page teaches the concept→build→playbook chain for skills.

**Answers:** What is a skill? When should I make one? How do I write a good SKILL.md? What goes wrong?

## Concept: what a skill is

A skill is a document — `SKILL.md` — that teaches the agent a multi-step workflow. After a complex task, Hermes can create skills on its own and improve them while it works. They are portable: the open `agentskills.io` standard. Where they live: `~/.hermes/skills/`, plus a Skills Hub for community skills.

```
memory (who you are)  ≠  skill (how to do a workflow)
```

Memory is a fact. A skill is a procedure.

## Decide: when to make one

Make a skill when:
- You just did a workflow you will repeat (research brief, content cut, repo summary).
- The workflow has 3+ steps or depends on a specific format.
- You want to trigger it from a fresh session or a cron job.

Do **not** make a skill for a one-off. Just prompt it.

## Build: two paths

**Path A — let it create itself.** After a successful task in chat:

```
This research-brief workflow worked well. Create a skill for it so I can
reuse it for any topic.
```

Hermes writes the `SKILL.md` in `~/.hermes/skills/`. Trigger anytime:

```
/research-brief "local LLMs on a laptop"
```

**Path B — write it by hand.** Use the Kynd starter-kit template:

```markdown
---
name: <skill-name>
description: Brief description of what this skill does
version: 1.0.0
metadata:
  hermes:
    tags: [<tag1>, <tag2>]
    category: <category>
---

# <Skill Title>

## When to Use
Use this skill when the user asks to <trigger condition>.

## Procedure
1. <step 1>
2. <step 2>
3. <step 3>

## Pitfalls
- Common failure: <description>. Fix: <solution>

## Verification
Run <check> to confirm the result is correct.
```

Once saved, the skill name becomes a slash command.

## Playbook: the skill shape that works

Every good Kynd skill has four parts:
1. **When to Use** — the exact trigger, so the agent loads it at the right time.
2. **Procedure** — numbered steps, each concrete.
3. **Pitfalls** — what breaks and the fix (this is what separates a real skill from a note).
4. **Verification** — how to confirm the output is correct (ties to [QA discipline](qa-discipline.md)).

## Example

The [Research Brief Agent](../case-studies/research-brief-agent.md) becomes a `research-brief` skill after one good run. Trigger: `/research-brief "vector databases"`. The skill encodes the AGENTS.md format so a cron job can run it unattended.

## What goes wrong

- **No "When to Use."** The agent never loads it. Always state the trigger.
- **No Pitfalls section.** The skill breaks the first time reality differs. Capture what failed.
- **Too generic.** "Help me with research" teaches nothing. "Research a topic, prefer primary sources, output the 7-section brief format" is a skill.
- **Forgetting cron is amnesic.** A scheduled job has no memory — the skill must be self-contained.

## Related

- The spine: [Context files](../foundation/context-files.md)
- Check the output: [QA discipline](qa-discipline.md)
- Real build: [Research Brief Agent](../case-studies/research-brief-agent.md)
- Source: course §3 (Skills) and §5 (Skill template)
