# KYND OS — PHASE 0 ARCHITECTURE COMPATIBILITY AUDIT (REVISED)

**Date:** 2026-08-31
**Auditor:** Hermes (builder profile)
**Revision:** 2 — reframed: Kynd is built on Hermes Agent
**Scope:** Read-only audit of 12 candidate repositories against kynd-runtime

---

# 1. EXECUTIVE SUMMARY (REVISED)

**Core insight: Kynd is not a standalone agent runtime. Kynd is a governance and control layer that sits on top of Hermes Agent.**

Hermes already provides everything an agent runtime needs:
- **Memory** — persistent facts across sessions (memory tool)
- **Scheduling** — cronjob tool with delivery, scripts, monitoring
- **Agent execution** — delegate_task, subagents, background processes
- **Tool execution** — terminal, web_search, web_extract, browser, computer_use, vision
- **Session history** — session_search for recalling past conversations
- **Skills** — procedural memory for recurring workflows

Kynd's job is to wrap all of that with **enforceable governance**: a constitution, a gate that validates every action before it happens, and a broker that caps spending, enforces allowlists, and audits everything.

This changes the audit fundamentally. Most candidates are now **irrelevant** because Hermes already provides the capability. The question shifts from "what should Kynd adopt?" to "what does Kynd need to ADD to Hermes?"

## Revised verdicts

| System | Original Verdict | Revised Verdict | Why |
|---|---|---|---|
| Mainspring | STUDY ONLY | **REJECT** | Session loop, memory, scheduling — Hermes does all of this. Nothing to adopt. |
| LangGraph | STUDY ONLY | **REJECT** | Checkpointing, state graphs — Hermes cron + sessions + memory cover the need. |
| Letta | VENDOR / STUDY | **REJECT** | Stateful agent runtime + memory — that IS Hermes. |
| n8n | VENDOR | **VENDOR** (smaller) | Still useful for 400+ integrations Hermes can't reach directly. But less critical — Hermes has terminal + web tools. |
| Temporal | VENDOR (defer) | **REJECT** | Durable execution — Hermes cron + background processes + launchd cover single-node. |
| Langfuse | ADAPT | **ADAPT** | Hermes has no structured LLM tracing. Langfuse still the right call. |
| Agent Platform | REJECT | **REJECT** | Still unverifiable. |
| Mem0 | ADAPT | **REJECT** | Memory layer — that's Hermes memory. Zero reason to add Mem0. |
| GAFF | STUDY ONLY | **REJECT** | MCP orchestration — Hermes has native MCP support. |
| LangChain | STUDY ONLY | **REJECT** | Agent framework — that's Hermes. |
| Agent OS | STUDY ONLY | **REJECT** | Verification is valuable, but Kynd should implement natively, not adopt a product. |
| BoringOS | STUDY ONLY | **REJECT** | Module system is interesting but irrelevant — wrong language, wrong scope. |

## Bottom line

Kynd needs to build **three things** on top of Hermes:

1. **Governance kernel** (the Python package: constitution + gate + broker)
2. **Observability** (Langfuse SDK — additive, non-intrusive)
3. **Integration connectors** (n8n for services Hermes can't reach — optional)

Everything else is already provided by Hermes. The audit is now a rejection memo for 10 of 12 candidates.

---

# 2. KYND CURRENT ARCHITECTURE ASSESSMENT (REVISED)

## What exists

### Kynd Runtime (Python package in workspace/kynd-runtime)
| Module | Status |
|---|---|
| `constitution.py` | Done — YAML load/validate, typed accessors |
| `broker.py` | Done — capability gates, caps, allowlists, audit, fail-closed |
| `governance_gate.py` | Done — hard-rule enforcement, action validation |
| Tests | Passing — constitution, broker, governance |

### Hermes Agent (the runtime Kynd builds on)
| Capability | How Hermes provides it |
|---|---|
| **Memory** | `memory` tool — persistent facts, session-scoped, searchable |
| **Scheduling** | `cronjob` tool — recurring jobs, one-shot, scripts, monitors |
| **Agent execution** | `delegate_task` — subagents, parallel, background |
| **Tool execution** | `terminal`, `web_search`, `web_extract`, `browser`, `computer_use`, `vision_analyze` |
| **Session history** | `session_search` — recall past conversations |
| **Skills** | `skill_manage` — procedural memory, reusable workflows |
| **Background processes** | `terminal(background=true)` + `process` management |

## What Kynd adds to Hermes

| Kynd primitive | What it does | Why Hermes needs it |
|---|---|---|
| **Constitution** | YAML-defined mission, hard rules, money caps | Hermes has no concept of "rules the brain cannot override" |
| **Governance gate** | Code validates every action before execution | Hermes tools execute freely — no policy layer |
| **Broker** | Capability-gated side effects with caps, allowlists, audit | Hermes has no spending caps, no target allowlists, no audit trail |

## Architecture fitness for Phase 0

**Fit.** The existing kernel is a solid foundation. The governance model (constitution + gate + broker) is the right abstraction. Everything this audit recommends adds **around** this kernel, not **into** it.

---

# 3. REVISED REPOSITORY AUDITS

---

## MAINSPRING (fablerlabs/mainspring)

**REVISED VERDICT: REASON**

Mainspring provides a session loop, constitution, memory, scheduling, and audit. Hermes already provides all of these:

| Mainspring capability | Hermes equivalent |
|---|---|
| Session loop (assemble → gate → dispatch → commit) | Hermes cron + delegate_task + session_search |
| Constitution (markdown rules) | Kynd constitution.py (YAML, typed, better) |
| Memory (STATE.md, journal) | Hermes memory tool |
| Scheduling (wake-up cycle) | Hermes cronjob tool |
| Audit log | Hermes session history + broker audit |
| Ledger (money tracking) | Kynd broker (caps, audit) |

**Nothing to adopt.** Mainspring is a standalone OS for agents that don't have a runtime. Kynd has Hermes.

---

## LANGGRAPH (langchain-ai/langgraph)

**REVISED VERDICT: REJECT**

LangGraph provides stateful graphs, checkpointing, and durable execution. Hermes covers the need:

| LangGraph capability | Hermes equivalent |
|---|---|
| StateGraph (typed state machine) | Hermes cron + scripts + background processes |
| Checkpoint-after-each-step | Hermes cron runs are atomic; session history provides trace |
| Crash recovery | launchd (already proven in kynd-os bot) + Hermes cron |
| Human-in-the-loop | Hermes approvals + Telegram/Discord notify |
| Thread model (multi-tenant) | Hermes profiles + deliver targets |

**Nothing to adopt.** LangGraph is for building agents from scratch. Kynd has Hermes.

---

## LETTA (letta-ai/letta)

**REVISED VERDICT: REJECT**

Letta provides stateful agents with memory that persists across sessions. That IS Hermes:

| Letta capability | Hermes equivalent |
|---|---|
| Stateful agent runtime | Hermes Agent (this is what it is) |
| Core memory (in-context) | Hermes memory tool (facts injected into context) |
| Archival memory (searchable) | Hermes session_search + memory search |
| Memory tools (append/replace/search) | Hermes memory tool (add/replace/remove/search) |
| Identity persistence | Hermes profile + persistent memory |

**Nothing to adopt.** Letta is a competitor to Hermes, not a complement to Kynd.

---

## N8N (n8n-io/n8n)

**REVISED VERDICT: VENDOR (smaller scope)**

n8n still has value for integrations Hermes can't reach directly. But the scope is smaller because Hermes already has terminal, web, and browser tools.

| n8n capability | Value to Kynd |
|---|---|
| 400+ integrations (Slack, Stripe, GitHub, etc.) | **High** — Hermes can't natively connect to all of these |
| Visual workflow editor | **Medium** — useful for debugging, not required |
| Webhook triggers | **Medium** — Hermes cron can poll, but webhooks are cleaner |
| DAG execution | **Low** — Hermes scripts + background processes cover this |

**Integration method:** Run n8n as external service. Kynd calls n8n via webhook for specific integrations (e.g., "create Stripe invoice," "post to Slack"). Hermes handles everything else natively.

**License note:** Sustainable Use License still requires legal review for SaaS redistribution.

---

## TEMPORAL (temporalio/sdk-python)

**REVISED VERDICT: REJECT**

Temporal provides durable execution with crash recovery. Hermes + launchd covers single-node:

| Temporal capability | Hermes equivalent |
|---|---|
| Automatic retries | Hermes cron retry + script-level retry logic |
| Crash recovery | launchd (KeepAlive, RunAtLoad) — already proven |
| Exactly-once execution | Idempotent cron design (clear_stale_proposals pattern from aios) |
| Event sourcing | Hermes session history + run ledger |
| Long-running workflows | Hermes background processes + process management |

**Nothing to adopt.** Temporal is for distributed multi-worker systems. Kynd on Hermes is single-node. Revisit only if Kynd needs multi-machine execution.

---

## LANGFUSE (langfuse/langfuse)

**REVISED VERDICT: ADAPT**

Hermes has no structured LLM tracing. Session history shows past conversations but not:
- Token usage and cost per call
- Nested trace spans (parent/child relationships)
- LLM-as-a-judge evaluation
- Prompt versioning
- Cost/latency/quality dashboards

Langfuse provides all of this with an additive SDK. The `@observe()` decorator wraps any function without changing its logic. Exit cost is low (remove decorators).

**Integration method:** Wrap Hermes brain calls, tool invocations, and broker decisions with Langfuse traces. Use LLM-as-a-judge for evaluation of agent outputs.

**Note:** Verify PostHog telemetry opt-out before production.

---

## AGENT PLATFORM

**REVISED VERDICT: REJECT**

Still unverifiable. No source material found.

---

## MEM0 (mem0ai/mem0)

**REVISED VERDICT: REJECT**

Mem0 provides a memory layer for AI agents. Hermes IS the memory layer:

| Mem0 capability | Hermes equivalent |
|---|---|
| `add(messages, user_id)` | Hermes memory tool (add facts) |
| `search(query, user_id)` | Hermes memory tool (search/recall) |
| LLM-powered fact extraction | Can be done with Hermes tools (terminal + LLM call) |
| Multi-level memory (user/session/agent) | Hermes memory is already scoped per-profile |
| Vector search | Not needed — Hermes memory is fact-based, not vector-based |

**Nothing to adopt.** Adding Mem0 would mean a second memory store alongside Hermes memory. That's duplication, not simplification.

---

## GAFF (seanpoyner/gaff)

**REVISED VERDICT: REJECT**

GAFF provides MCP orchestration — a gateway to multiple MCP servers. Hermes has native MCP support:

| GAFF capability | Hermes equivalent |
|---|---|
| MCP server gateway | Hermes native_mcp skill (already connects to MCP servers) |
| Intent graph generation | Not needed — Hermes tools are explicit |
| Safety protocols | Kynd governance gate (better — code-enforced, not scaffolded) |
| Quality checks | Kynd verification layer (build/test passes) |

**Nothing to adopt.** Hermes already does MCP. Kynd's gate is better than GAFF's "scaffolded" safety.

---

## LANGCHAIN (langchain-ai/langchain)

**REVISED VERDICT: REJECT**

LangChain is an agent framework. Hermes IS the agent framework:

| LangChain capability | Hermes equivalent |
|---|---|
| `@tool` decorator | Hermes tools (terminal, web_search, etc.) |
| ChatModel abstraction | Hermes model routing (provider:model syntax) |
| AgentExecutor / ReAct loop | Hermes delegate_task + subagents |
| 200+ model integrations | Hermes model gateway (OpenAI, Anthropic, etc.) |
| Vector store integrations | Not needed — Hermes memory is fact-based |

**Nothing to adopt.** LangChain is a competitor to Hermes, not a complement to Kynd.

---

## AGENT OS (earthwalker17/agent-os)

**REVISED VERDICT: REJECT**

Agent OS provides verification-as-ground-truth, which is the most valuable pattern in this audit. But Kynd should implement it natively, not adopt a full product:

| Agent OS capability | Value to Kynd |
|---|---|
| Verification-as-ground-truth | **Critical** — Kynd must adopt this pattern |
| Recovery Matrix | **Medium** — useful for retry classification |
| Memory engine | **None** — Hermes memory |
| Coding agent runner | **None** — wrong domain |
| Browser verification | **None** — wrong domain |

**Action:** Study the verification pattern. Implement natively in Kynd's orchestrator. Reject the product.

---

## BORINGOS (BoringOS-dev/boringos)

**REVISED VERDICT: REJECT**

BoringOS is a full product (shell, CRM, inbox, workflows). Kynd is a governance kernel. Wrong scope, wrong language, too new.

| BoringOS capability | Value to Kynd |
|---|---|
| Module system (skills + tools + schema) | **Low** — interesting pattern, but Kynd's tools are Hermes tools |
| Budget enforcement | **None** — Kynd broker already does this |
| Agent-as-CLI-subprocess | **None** — Hermes IS the agent |
| Visual workflow DAGs | **None** — wrong layer |

**Nothing to adopt.** Study the module system pattern if you're curious. Move on.

---

# 4. OVERLAP MATRIX (REVISED)

## Kynd vs Hermes vs Candidates

| Capability | Kynd | Hermes | Mainspring | LangGraph | Letta | n8n | Temporal | Langfuse | Mem0 | GAFF | LangChain | Agent OS | BoringOS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Governance** | **●** | ○ | ● | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ● |
| **Memory** | ○ | **●** | ● | ○ | ● | ○ | ○ | ○ | ● | ○ | ○ | ● | ○ |
| **Orchestration** | ○ | **●** | ● | ● | ○ | ○ | ● | ○ | ○ | ● | ● | ● | ● |
| **Tool Execution** | ○ | **●** | ○ | ○ | ● | ● | ○ | ○ | ○ | ● | ● | ● | ● |
| **Scheduling** | ○ | **●** | ● | ○ | ○ | ● | ○ | ○ | ○ | ○ | ○ | ○ | ○ |
| **Observability** | ○ | ○ | ○ | ○ | ○ | ○ | ● | **●** | ○ | ○ | ○ | ○ | ○ |
| **Evaluation** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | **●** | ○ | ○ | ○ | ● | ○ |
| **Integrations** | ○ | ● | ○ | ○ | ○ | **●** | ○ | ○ | ○ | ○ | ● | ○ | ● |
| **Agent Runtime** | ○ | **●** | ● | ● | ● | ○ | ○ | ○ | ○ | ○ | ● | ● | ● |
| **MCP** | ○ | **●** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ○ | ○ | ○ |
| **Verification** | **○** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● | ○ |

**Key:** ● = provides this capability ○ = does not

**The pattern:** Hermes covers 9 of 11 capabilities. Kynd covers 1 (governance) and needs to add 1 (verification). Langfuse covers 1 (observability/evaluation) that Hermes doesn't. n8n covers 1 (integrations) that Hermes partially covers.

**Everything else is duplication.**

---

# 5. KYND NATIVE VS EXTERNAL ANALYSIS (REVISED)

## Kynd should own (build internally, core product)

| Capability | Rationale |
|---|---|
| **Constitution** | Already done. The agent's rules are Kynd's core product differentiator. |
| **Governance gate** | Already done. Code-enforced rules are Kynd's security model. |
| **Broker** | Already done. Capability-gated side effects with audit are Kynd's execution model. |
| **Verification** | Must build natively. "Done means build/test passes, not model says so." |

## Kynd should integrate (external infrastructure, significant effort reduction)

| Capability | External Choice | Rationale |
|---|---|---|
| **Observability** | Langfuse SDK | Tracing, cost tracking, evaluation. Non-intrusive, additive, low lock-in. Hermes has no equivalent. |
| **Integrations** | n8n (external service) | 400+ connectors for services Hermes can't reach directly. Optional — many integrations can be done with Hermes terminal + web tools. |

## Kynd should study (architectural patterns worth learning, not adopting)

| Source | Pattern | Why not adopt |
|---|---|---|
| **Agent OS** | Verification-as-ground-truth | Full product, wrong domain. Implement pattern natively. |
| **BoringOS** | Module system (skills + tools + schema) | TypeScript, too new, too small. Pattern is clean but irrelevant. |

## Kynd should reject (duplication of Hermes or irrelevant)

| System | Reason |
|---|---|
| **Mainspring** | Session loop, memory, scheduling — all Hermes. |
| **LangGraph** | State graphs, checkpointing — all Hermes. |
| **Letta** | Stateful agent runtime + memory — that IS Hermes. |
| **Temporal** | Durable execution — Hermes cron + launchd covers single-node. |
| **Mem0** | Memory layer — that's Hermes memory. |
| **GAFF** | MCP orchestration — Hermes native MCP. |
| **LangChain** | Agent framework — that's Hermes. |
| **Agent Platform** | Unverifiable. |
| **agentxagi/Agent OS** | Vapor (3 commits, 0 stars). |

---

# 6. MINIMAL PRODUCTION STACK (REVISED)

```
KYND OS
│
├── Hermes Agent ──────────────────── PROVIDED (runtime, memory, scheduling, tools)
│   ├── Memory (persistent facts)
│   ├── Cron (scheduling)
│   ├── Delegate (subagents)
│   ├── Tools (terminal, web, browser, vision)
│   └── Session history
│
├── Kynd Governance Kernel ────────── KYND OWNED (Python package)
│   ├── Constitution (YAML rules)
│   ├── Governance Gate (validate)
│   ├── Broker (caps, allowlists, audit)
│   └── Verification (build/test passes)
│
├── Langfuse SDK ──────────────────── INTEGRATE (observability, evaluation)
│
└── n8n (external) ────────────────── VENDOR (400+ integrations, optional)
```

### Stack summary

| Component | Count | Source |
|---|---|---|
| Major runtime systems | 1 (Hermes) | Provided |
| Governance kernel | 1 (Kynd) | Build |
| Databases | 0 (Hermes memory is file-based) | Provided |
| Background services | 0 (Hermes cron) | Provided |
| External dependencies | 1 (Langfuse SDK) | Integrate |
| Deployment units | 1 (Hermes + Kynd) | — |
| Operational responsibilities | 1 (run Hermes) | Provided |

### What this stack provides

| Requirement | How |
|---|---|
| Reliable execution | Hermes cron + launchd + idempotent cycles |
| Memory | Hermes memory tool |
| Tool use | Hermes tools (terminal, web, browser, vision) |
| Approvals | Kynd broker + governance gate |
| Integrations | Hermes tools + optional n8n |
| Recovery | Hermes cron retry + launchd auto-restart |
| Observability | Langfuse SDK |
| Evaluation | Langfuse evals |
| Security | Kynd constitution + gate + broker (fail-closed) |
| Auditability | Kynd broker audit log + Langfuse traces |
| Verification | Kynd native (build/test passes) |

---

# 7. COMPLEXITY BUDGET (REVISED)

| Metric | Value |
|---|---|
| Major runtime systems | 1 (Hermes) |
| Governance kernel | 1 (Kynd Python package) |
| Databases | 0 (Hermes memory is file-based) |
| Background services | 0 (Hermes cron) |
| External dependencies | 1 (Langfuse SDK) |
| Deployment units | 1 (Hermes + Kynd) |
| Major operational responsibilities | Run Hermes |
| Main failure points | LLM API, n8n webhook delivery (if used) |

## Is this architecture too complex for Kynd at its current stage?

**No.** This is the minimal viable stack. Kynd is a governance kernel + one optional observability SDK. Everything else is Hermes. The complexity budget is as tight as it gets.

---

# 8. SECURITY / LICENSE / MAINTENANCE RED FLAGS (REVISED)

## License conflicts

| System | License | Conflict? |
|---|---|---|
| Kynd Runtime | MIT | — |
| Hermes Agent | MIT | — |
| Langfuse | MIT (core), AGPL (ee/) | Avoid ee/ features |
| n8n | Sustainable Use License | **YES** — commercial redistribution requires n8n license. Legal review if SaaS. |

## Security concerns

| Concern | System | Severity |
|---|---|---|
| Langfuse telemetry to PostHog | Langfuse | Low — documented, opt-out available, verify |
| n8n community nodes vary in quality | n8n | Medium — audit nodes before use |
| Kynd governance gate bypass | Kynd | **Critical** — if the gate can be bypassed, the whole security model fails. Test thoroughly. |

## Abandoned repositories

All candidates except Langfuse and n8n are rejected. No adoption risk.

## Duplicate systems

**The whole point of this revision.** 10 of 12 candidates duplicate Hermes capabilities. Reject all 10.

## Architectural contradictions

| Contradiction | Resolution |
|---|---|
| Kynd is a governance layer; adopting another runtime makes Kynd a guest | Reject all runtime candidates (Mainspring, LangGraph, Letta, LangChain, BoringOS, Agent OS) |
| Kynd is Python; several candidates are TypeScript | Reject all TypeScript candidates (Mainspring, BoringOS, GAFF) |
| Kynd is minimal; several candidates are full platforms | Reject all platform candidates (Letta, LangChain, n8n is borderline) |

---

# 9. RECOMMENDED FINAL ARCHITECTURE (REVISED)

```
                         KYND OS
                            │
                ┌───────────┴───────────┐
                │                       │
          KYND GOVERNANCE          HERMES AGENT
        Constitution / Rules       (runtime, memory,
        Gate / Broker / Verify      tools, scheduling)
                │                       │
                └───────────┬───────────┘
                            │
                            ▼
                      ORCHESTRATOR
                    (Hermes cron +
                     delegate_task)
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           AGENTS        AGENTS        AGENTS
         (Hermes       (Hermes       (Hermes
          subagents)    subagents)    subagents)
              │             │             │
              └─────────────┼─────────────┘
                            ▼
                       ACTION LAYER
               ┌────────────┼────────────┐
               ▼            ▼            ▼
         Hermes Tools   Hermes Tools   n8n (ext)
         (terminal,     (browser,      (400+ APIs)
          web, vision)   computer_use)
               │            │            │
               └────────────┼────────────┘
                            ▼
                      EXTERNAL SYSTEMS
                            │
                            ▼
                         MEMORY
                    (Hermes memory tool)
                            │
                            ▼
                       KYND BRAIN
                            ↺

             OBSERVABILITY / EVALUATION
                  Langfuse wraps entire system
```

### Legend

- **KYND OWNED:** Constitution, Governance Gate, Broker, Verification
- **HERMES PROVIDED:** Memory, Cron, Tools, Subagents, Session history
- **INTEGRATE:** Langfuse SDK (observability, evaluation)
- **VENDOR (optional):** n8n (integrations)

---

# 10. RECOMMENDED INTEGRATION ORDER (REVISED)

## Step 1: Wire Kynd governance into Hermes tool calls

**COMPONENT:** Make every Hermes tool call go through Kynd's broker
**WHY NOW:** Without this, Hermes tools execute freely — no governance.
**DEPENDENCIES:** Kynd Runtime Python package (already built)
**WHAT IT ENABLED:** Constitution-enforced tool execution
**WHAT MUST NOT BE BUILT YET:** New tools, new integrations
**SUCCESS CRITERIA:** A terminal command that violates the constitution is blocked before execution. The audit log records the denial.

## Step 2: Verification layer

**COMPONENT:** Verification-as-ground-truth (build/test must pass for "done")
**WHY NOW:** Without this, the model can self-certify its own work.
**DEPENDENCIES:** None (verification is code that runs)
**WHAT IT ENABLED:** Trustworthy agent output
**WHAT MUST NOT BE BUILT YET:** Recovery Matrix, browser verification
**SUCCESS CRITERIA:** A task is marked "completed" only after a real verification step passes. The model cannot claim success without proof.

## Step 3: Langfuse observability

**COMPONENT:** `@observe()` decorator on brain calls, tool invocations, broker decisions
**WHY NOW:** Once agents run in production, debugging requires traces.
**DEPENDENCIES:** `langfuse` Python package, Langfuse server (self-hosted or cloud)
**WHAT IT ENABLES:** Trace inspection, cost tracking, evaluation
**WHAT MUST NOT BE BUILT YET:** Custom dashboards, alerting
**SUCCESS CRITERIA:** Every agent run produces a Langfuse trace. Cost per run is tracked.

## Step 4: n8n integrations (optional)

**COMPONENT:** n8n as external integration engine
**WHY NOW:** Only when Hermes tools can't reach a needed service.
**DEPENDENCIES:** n8n service (separate), webhook configuration
**WHAT IT ENABLES:** 400+ integrations without building connectors
**WHAT MUST NOT BE BUILT YET:** Custom n8n nodes, native MCP gateway
**SUCCESS CRITERIA:** Kynd can trigger an n8n workflow via webhook for a specific integration (e.g., Stripe, Slack).

---

# 11. PHASE 0 DECISION GATE (REVISED)

## PHASE 0 DECISION: **GREEN**

Architecture is sufficiently understood. Implementation can begin.

### The single most important architectural decision Kynd must make before coding is:

> **How does Kynd's broker intercept Hermes tool calls?**

Options:
1. **Wrapper pattern** — Kynd provides a `kynd_execute(tool_name, params)` function that Hermes scripts call instead of raw tools. The wrapper checks the gate, calls the broker, then executes.
2. **Proxy pattern** — Kynd sits between Hermes and the tools, intercepting all calls. Harder to implement, more transparent.
3. **Constitution-only pattern** — Kynd defines the constitution, but Hermes tools execute freely. The gate is advisory, not enforced. (Weak — defeats the purpose.)

**Recommendation:** Wrapper pattern. Kynd exposes a single `kynd.execute(capability, action, params)` function. Hermes scripts call this instead of raw tools. The function checks the constitution, validates against the gate, requests broker approval, executes the tool, and records the audit entry. Simple, explicit, testable.

### The three highest risk assumptions still requiring validation are:

1. **The wrapper pattern is enforceable.** Risk: Hermes scripts can still call raw tools directly, bypassing Kynd. Mitigation: Make Kynd the default execution path in Hermes skills. Document that raw tool calls are for infrastructure only. Audit for bypasses.

2. **Hermes memory is sufficient for Kynd's Business Brain.** Risk: Fact-based memory may not capture complex relationships (e.g., "Franco's agency has 18 leads, 3 in proposal stage, with a combined pipeline value of $47k"). Mitigation: Test with real business data. If structured queries are needed, add a lightweight projection layer (read-only views over memory facts).

3. **Langfuse's PostHog telemetry can be fully disabled.** Risk: If telemetry cannot be disabled, Langfuse sends usage data to a third party. Mitigation: Inspect Langfuse source code and confirm the opt-out mechanism before production.

---

# APPENDIX A: VERDICT SUMMARY (REVISED)

| System | Verdict | Confidence |
|---|---|---|
| Mainspring | REJECT | High |
| LangGraph | REJECT | High |
| Letta | REJECT | High |
| n8n | VENDOR (optional) | High |
| Temporal | REJECT | High |
| Langfuse | ADAPT | High |
| Agent Platform | REJECT | Low |
| Mem0 | REJECT | High |
| GAFF | REJECT | High |
| LangChain | REJECT | High |
| Agent OS | REJECT | High |
| BoringOS | REJECT | Medium |

**10 rejections, 1 adapt, 1 vendor (optional).**

# APPENDIX B: WHAT KYND ACTUALLY NEEDS TO BUILD

| Component | Effort | Priority |
|---|---|---|
| Wire Kynd broker into Hermes tool calls (wrapper pattern) | Small | P0 |
| Verification layer (build/test passes) | Small | P0 |
| Langfuse SDK integration | Small | P1 |
| n8n webhook connector | Medium | P2 (optional) |

**Total: ~2 weeks of work to production governance.**

# APPENDIX C: UNVERIFIED ITEMS REQUIRING FOLLOW-UP

1. Langfuse PostHog telemetry opt-out mechanics
2. Whether Hermes memory can handle structured business queries (pipeline value, lead counts)
3. n8n Sustainable Use License terms for SaaS redistribution
4. Whether the wrapper pattern can be made the default execution path in Hermes skills

---

*End of Phase 0 Architecture Compatibility Audit (Revised)*
*Generated: 2026-08-31*
*Auditor: Hermes (builder profile)*
*Status: Read-only audit. No code modified.*
*Revision: 2 — reframed: Kynd is built on Hermes Agent*
