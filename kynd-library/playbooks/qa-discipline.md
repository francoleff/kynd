# QA discipline

Agents are confidently wrong. They invent sources, misread files, and declare victory on broken output. If you trust agent output without checking, you will eventually ship something false. This playbook is the habit that keeps you safe.

**Answers:** Why must I check agent output? What do I check? What is the fastest QA pass? What do I do when I find a fabrication?

## Why this matters

An LLM optimizes for plausible text, not truth. Given a missing fact, it will often fill the gap with something that sounds right. In the Kynd course this is non-negotiable: every research brief rule says *"never invent facts, quotes, or sources"* and *"mark unverifiable claims `[UNVERIFIED]`."* The rules reduce the risk. They do not remove it. You verify.

## The QA template (use it on everything)

From the Kynd starter kit. Run it before you trust or publish anything the agent produces:

```markdown
OUTPUT CHECKED: <what was produced>
ACCURACY: <did you spot-check claims? how many links followed?>
COMPLETENESS: <does it answer the original task?>
FORMAT: <does it match the spec?>
FABRICATIONS: <any invented facts/quotes/sources? : list them>
VERDICT: <ship / fix these items / redo>
```

## The fastest pass (60 seconds)

When you are in a hurry, do at least these three:

1. **Spot-check 2+ source links.** Click them. Does the claim match the page? This alone catches most fabrications.
2. **Confirm the format matches the spec.** If your `AGENTS.md` says "7 sections," count them.
3. **Ask "what would be embarrassing if wrong?"** Anything in that bucket gets a closer look.

## A one-line prompt that forces QA

Tell the agent to check itself before it finishes:

```
QA my output in <file> against the spec in <AGENTS.md>. Check accuracy
(spot-check links), completeness, format, and fabrication. Report a verdict:
ship / fix these items / redo.
```

You still verify the verification — but the agent's self-check surfaces the obvious misses.

## Red-team for bigger builds

For anything that touches money, customers, or production:

```
Red-team my <system/plan>: list the 5 most likely failure points, what each
would cost, and the cheapest mitigation.
```

## What goes wrong

- **"It sounded right."** Sound ≠ true. Always spot-check.
- **Trusting the format as proof of correctness.** A perfectly formatted brief can still cite a fake paper.
- **Skipping QA on cron output.** Scheduled jobs run unattended — the output lands in a file you might not open for days. Build the QA step into the job's prompt, or review on a schedule.
- **Not marking [UNVERIFIED].** If the agent cannot verify a claim, the honest move is to label it, not to drop it.

## Related

- The spine: [Context files](../foundation/context-files.md)
- Make it reusable: [Building skills](building-skills.md)
- Real build with QA baked in: [Research Brief Agent](../case-studies/research-brief-agent.md)
- Source: course §5 (QA template) and §7 (QA prompts)
