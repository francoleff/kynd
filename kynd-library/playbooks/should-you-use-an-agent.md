# Should you use an agent for this?

The fastest way to waste a week is to build an agent for a task that does not need one. This is the gate you run before the [Problem-First Method](problem-first-method.md). If the answer is "no," you just saved yourself a project.

## The five-question filter

Answer each. If you say "yes" to the task on the left and "no" to the warning on the right, an agent is a good fit.

| # | Question | Skip the agent if… |
|---|----------|--------------------|
| 1 | Is this a **repeatable task** you actually do? | It is a one-off you will never touch again. |
| 2 | Does it involve **judgment, research, or messy input**? | It is a fixed formula a spreadsheet runs in one cell. |
| 3 | Is the **input and output clear** enough to describe "done"? | You cannot say what success looks like. |
| 4 | Can it be **broken into small steps**? | It is one giant ambiguous blob with no parts. |
| 5 | Is the **cost of a mistake** low enough to iterate? | One wrong move deletes a database or sends money. |

Three or more "yes" → build it. One or two → probably not worth an agent yet.

## The three traps

**Trap 1 — The spreadsheet trap.** If the task is "multiply column A by column B and email the result," that is a formula and a mail-merge. An agent adds risk and latency for zero gain. Use the simpler tool.

**Trap 2 — The demo trap.** "I made an agent that writes poetry" is a demo. "I made an agent that turns my inbox into a one-line morning brief" is a build. Demos feel productive and produce nothing. Aim for the brief, not the poem.

**Trap 3 — The big-blob trap.** "Build me a system that runs my whole business" fails. "Summarize the three longest unread emails" works. Start at the size a human could do in twenty minutes, then expand. See [Understand AI agents](../foundation/understand-ai-agents.md) — agents are not reliable on long ambiguous tasks without checkpoints.

## A worked sort

- "Research a competitor before every pitch." → Repeatable ✓, involves judgment ✓, "done" = a brief ✓, breakable into steps ✓, mistake cost low ✓. **Build it.** (This is the [Research Brief Agent](../case-studies/research-brief-agent.md).)
- "Send a birthday email to my mom." → One-off, fixed content. **Skip.** A calendar reminder does it.
- "Auto-trade my portfolio." → Mistake cost is catastrophic. **Not yet** — and maybe never unattended.
- "Turn my meeting notes into action items." → Repeatable, messy input, clear output, breakable, low cost. **Build it.**

## What to do after the filter

If you got three "yes": write the task and what "done" looks like, then run the [Problem-First Method](problem-first-method.md). If you got one or two: do it manually this time, and only automate once the pattern repeats.

The point is not to use agents everywhere. It is to use them where they remove friction you actually feel.
