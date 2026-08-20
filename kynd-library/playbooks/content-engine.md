# Content engine (one pillar, four platforms)

Kynd's publishing system. You write one deep essay, then cut it into four platform posts. This is how Kynd ships consistent content without writing four separate pieces from scratch.

**Answers:** What is the content engine? What is the structure of each post? When do I publish? How does Kynd actually run it?

## The shape

```
SUBSTACK essay  (the pillar — the deep version)
   ├── X thread        (the reach engine)
   ├── LinkedIn post   (the authority cut)
   └── Reddit story    (value first, no link)
```

One essay. Four outputs. Same core argument, rewritten for each place.

## The structure of every post

1. **Hook** — open with an observation. "Everyone is waiting for permission."
2. **The enemy** — name the false belief and dismantle it. "You need credentials first." Wrong.
3. **The advantage** — bring in the [Problem-First Method](problem-first-method.md) and Kynd. State it as fact.
4. **Three steps** — the actionable core.
5. **One CTA** — a single call to action.

## One CTA per platform

| Platform | CTA |
|----------|-----|
| Substack | Reply / join the free Discord |
| X | Comment → I send the invite |
| LinkedIn | Comment → I send the invite |
| Reddit | None. Answer questions, build trust |

Reddit gets no link. You provide value, answer questions, and let trust do the work.

## The remix method (when you borrow a structure)

Kynd sometimes remixes strong existing structures (e.g. Dan Koe's pre-fame tweets) into Franco's voice. The method:

1. Extract the core claim.
2. Swap the situation to Kynd's world (AI agents, the problem-first method, building instead of the default path).
3. Keep the structure, rhythm, and punch.
4. Check against the voice rules. Never copy the words — remix them.
5. State it as fact.

## Voice rules (non-negotiable)

- Open with an observation. Ask mid-post questions ("How?", "Why?", "The truth?").
- Short lines. Whitespace is the signature. Let thoughts breathe.
- Plain facts, no guru energy, no theater.
- State the positive directly. Never "not this, but that."
- Never claim "I run my agency with an agent." Say "I build with AI agents." The agency stays out.
- No mental-health confession.
- One CTA per post.
- Space every punctuation mark from the word ("word ," "word ."). Exactly like Franco types.

If you would not say it out loud, cut it.

## Timing

Publish the pillar (Substack) as Post Zero, then the thread and LinkedIn the same day. Reddit a day later, no link — so it does not read as a spam wave. Every comment gets the Discord invite. Nothing else.

## How Kynd actually runs it

Franco built a real tool for this: the [Kynd Content Engine](../case-studies/kynd-content-engine.md) — a local Python script (`content-engine/engine.py`) that takes one topic and generates all four cuts in his enforced voice, with a guard that refuses banned words and bio framing. It writes files; it never posts. That is the [Problem-First Method](problem-first-method.md) applied to content: name the repetitive task (weekly rewrite), describe "done" (four voice-correct cuts), automate it.

## Why this is in a builder library

Building is half the game. The other half is showing your work so a tribe forms around it. This engine turns one writing session into a week of reach. It pairs with the [Content System build](../build/hermes-starter-path.md) if you want to automate the draft stage.
