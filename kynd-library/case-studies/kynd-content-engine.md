# Case study: the Kynd Content Engine

A real Kynd-built tool. Franco replaced a manual, weekly chore — rewriting one essay into four platform posts — with a local Python script. This is the [Problem-First Method](../playbooks/problem-first-method.md) applied to content: name the repetitive task, describe "done," automate it.

Source: `content-engine/engine.py` in this workspace. The script is real and readable. Everything below is taken from it.

## What it is

A deterministic generator. You feed it one topic (and optionally a remix line). It writes all four platform cuts — Substack pillar, X thread, LinkedIn post, Reddit story — in Franco's enforced voice. It writes files to `generated/<topic-slug>/`. It never posts, never deploys.

```
python3 engine.py --topic "why beginners stall with AI agents" --cta-link https://join-kynd.netlify.app
python3 engine.py --topic "..." --remix "Most people adopt a routine they repeat until 80"
python3 engine.py --topic "..." --dry-run        # print, no files
python3 engine.py --list-topics                   # show what's been generated
```

## Why this one

- **Repetitive task.** Every week, the same pillar→four-cuts rewrite. Manual, easy to skip, easy to drift off-voice.
- **Clear "done."** Four cuts, each in the right structure, each one CTA, all in voice.
- **Low mistake cost.** It writes files locally; a human reviews before anything goes live. Nothing is posted automatically.

That is a textbook Problem-First build — exactly the filter in [Should you use an agent for this?](../playbooks/should-you-use-an-agent.md).

## The voice guard (the clever part)

The engine enforces Franco's voice in code, not just in instructions. Two mechanisms:

1. **Spaced punctuation.** A `spaced()` function rewrites text so every mark (`, . ? !`) gets its own space and the next sentence is capitalized. This bakes the "word , word ." style into the output.
2. **Banned-token guard.** A `guard()` function raises and aborts if any banned bio framing (`18`, `dropped out`, `no degree`, `broke`, `no savings`, `no network`, `just shipping`) or banned word (`ship`, `guru`, `annoying task`, `building in public`) appears. It refuses to write output that breaks the voice rules.

This is a reusable lesson: **encode your standards as a check, not a hope.** The agent (or script) cannot drift if the guard blocks the drift.

## How the cuts are structured

Every cut follows the playbook from [Content engine](../playbooks/content-engine.md):

- **Hook** — observation about AI communities being courses or flexing.
- **Enemy** — the false belief that you need credentials first.
- **Advantage** — Kynd as a free place to build, beginners welcome.
- **CTA** — one link, once. Reddit gets no link (value first).

The script does not "write" creatively — it assembles these fixed blocks around the topic. That is why it stays on-voice: the structure is the voice.

## What usually goes wrong (and how it is handled)

- **Off-voice drift.** Handled by the `guard()` abort. If a remix seed contains a banned word, the run fails loudly instead of shipping a bad post.
- **Forgetting the "one CTA" rule.** Baked in: each cut ends with exactly one link (Reddit: none).
- **Posting something un-reviewed.** Prevented by design: the script only writes files. Publishing is a separate, human step.

## Lessons to steal

1. **Automate the repetitive, keep the judgment.** The engine drafts; a human posts. The standard from [QA discipline](../playbooks/qa-discipline.md) still applies to the human step.
2. **Encode standards as guards.** If a rule matters, make breaking it impossible, not just advised.
3. **Structure is voice.** Fixed blocks (hook→enemy→advantage→CTA) keep output consistent without a giant prompt.
4. **Local-only, no side effects.** A content tool that can't accidentally post is a tool you can run without fear.

## Related

- The method: [Problem-First Method](../playbooks/problem-first-method.md)
- The playbook: [Content engine](../playbooks/content-engine.md)
- The decision: [Should you use an agent for this?](../playbooks/should-you-use-an-agent.md)
- Build your own: [Hermes starter path](../build/hermes-starter-path.md)

> Note: the script's output quality depends on the topic and remix seed you give it. It is a drafting aid, not a replacement for editorial judgment.
