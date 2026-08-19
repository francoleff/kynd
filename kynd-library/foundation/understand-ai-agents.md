# Understand AI agents

You do not need a computer science degree to use an AI agent. You need the mental model. This page gives you that in five minutes.

## The one sentence version

An AI agent is a program that uses a large language model (LLM) as its brain, and gives that brain **hands** — the ability to search the web, read and write files, run code, and talk to other apps — so it can actually do things, not just chat about them.

## The two parts people mix up

- **The model** is the brain. It reads and writes text. Examples: GPT-4o, Claude, Gemini, Llama. It is smart but stuck inside a chat box.
- **The harness** is the body. It is the program that runs the model and connects it to tools. The harness is what lets the model "do" things in the real world.

You can swap the brain. The same harness can run a cheap model or a frontier model. The harness is the part that matters for building.

## What an agent can actually do

A good agent harness gives the model these kinds of hands:

- **Web search** — find current information, not just training data.
- **Files** — read your notes, write a report, edit code.
- **Terminal / code** — run a script, install a package, test something.
- **Browser** — open a page, click, fill a form, scrape data.
- **Memory** — remember you across sessions, not start blank every time.
- **Schedule** — run on a timer. "Every Monday, write me a briefing."
- **Delegation** — spawn smaller agents that work in parallel and report back.
- **Connections (MCP)** — talk to databases, GitHub, your own APIs.

The model decides what to do. The harness does it.

## What an agent cannot do (yet)

- It is not reliable on long, ambiguous tasks without checkpoints. Break big tasks into small ones.
- It can be wrong confidently. Verify the output, especially anything it ran.
- It does not "know" your business unless you give it context. Memory and good instructions fix most of this.
- It cannot make a decision you have not framed. That is your job — which is exactly what the [Problem-First Method](../playbooks/problem-first-method.md) is for.

## Why this matters for you

Most people stop at the chatbot. They ask it to write an email and copy-paste. An agent closes the loop: it writes the email, sends it, logs it, and tells you it is done. That difference — **doing vs. describing** — is the entire game.

## Next

- New to the words? Read the [Kynd glossary](kynd-glossary.md).
- Ready to build? The [Problem-First Method](../playbooks/problem-first-method.md) is the fastest way to start.
- Want the concrete path? [Build your first agent](../build/hermes-starter-path.md).
