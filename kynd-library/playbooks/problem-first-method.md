# The Problem-First Method

This is the only framework you need to start building with AI agents. It is Kynd's core method. It exists because most people start backwards: they learn a tool, then hunt for a problem. That produces toy projects that die in a week.

Start with the problem. Always.

## The method in three steps

### 1. Name one real task you already do

Not a dream project. A boring, repeatable thing you actually did this week.

- "I summarize every customer email before I reply."
- "I research a competitor every time we pitch."
- "I turn my messy notes into a clean to-do list."

If you would pay someone $5 to do it, it counts. The smaller and more real, the better.

### 2. Write what "done" looks like

In plain words, like you are explaining it to a friend. Say:
- What the input is (an email, a link, a file).
- What the output is (a summary, a table, a draft).
- What to do when it goes wrong (try again, ask me, stop).

You are not writing code. You are writing the spec a smart intern would need.

### 3. Talk to an AI and tell it what you want

Open an agent. Paste the task and your "done" description. Ask it to do the thing.

Then **iterate three times**:
- It fails → copy the error, ask what to try next, try again.
- It is close → tell it what is wrong, specifically.
- It works → save what you did. That saved thing is now a reusable asset.

Three tries, every time. Most problems crack by the third.

## Why this works

- You never build something nobody needs. The task is real, so the win is real.
- You learn the tool *through* the task, not in a vacuum.
- Every solved problem becomes a document. Every document becomes an asset. Over time you accumulate a toolkit that is yours.

Before you start, run the [Should you use an agent for this?](should-you-use-an-agent.md) filter. If the task is a one-off or a fixed formula a spreadsheet handles, skip the agent and do it by hand. The method below assumes you already have a real, repeatable task.

## A worked example

**Task:** "Summarize the three longest unread emails in my inbox into one bullet list."

**Done looks like:** A short list. One bullet per email. Each bullet: who, what they want, whether I need to act. Output to a file called `brief.md`.

**Three iterations:**
1. First try: it summarizes all emails, not just the three longest. You say "only the three longest." It complies.
2. Second try: bullets are too long. You say "one sentence each." Better.
3. Third try: it writes the file. You open it. Correct. You save the prompt as a reusable asset.

That is a build. Not a course. A thing you will use Monday.

## Connect it

- Stuck on what to build? See [Understand AI agents](../foundation/understand-ai-agents.md) for what agents can do.
- Want the concrete path to a working agent? [Build your first agent](../build/hermes-starter-path.md).
- See it applied: [Research Brief Agent case study](../case-studies/research-brief-agent.md).
