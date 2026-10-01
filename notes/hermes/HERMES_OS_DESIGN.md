# Hermes Autonomous Operating System — Design v1

Hermes is the founder's personal AI operating system. Goal: a one-person company that runs
partially on autopilot — research, briefing, execution, review, and opportunity discovery
happen without the founder manually triggering each one.

## 1. Operating Instructions (improved)
- Default to action over planning. When a request is concrete, build the artifact, don't describe it.
- Prefer parallel subagents for research-heavy / independent work; keep synthesis in the main loop.
- Every deliverable is a file or a running system, never just a chat answer.
- Verify with real tool output before claiming done. No fabricated results.
- Batch independent tool calls. Serialize only on true dependencies.

## 2. Memory Architecture
- Three stores: `memory` (durable facts/quirks), `user` (who the user is), `skills` (procedures).
- Add a fourth: `projects/<name>/state.md` — living project state (current focus, blockers, next action).
  Loaded at session start when working on that project.
- Memory entries must be declarative + stable >7 days. Never store task progress or stale IDs.
- Weekly review prunes memory; monthly review consolidates patterns into skills.

## 3. Task Management
- Single source of truth: `/Users/francoleff/KYND/` task files (roadmap.md, tasks.md, TODO).
- Each task: id, owner (founder|agent), status, due, leverage score (1-10), blocks.
- Daily execution agent pulls top-3 by leverage. Weekly review re-scores.
- Agent-created tasks land in `tasks.md` with `[agent]` tag for founder ratification.

## 4. Delegation System
- Leaf agents for isolated research/build. Orchestrator only when a child must spawn its own workers.
- Every delegated task ships a self-contained `goal` + `context` (children know nothing else).
- Require a verifiable handle (URL/file path) for any external side effect; verify before reporting success.

## 5. Automation Workflows (cron)
Registered as local cron jobs writing to `/Users/francoleff/KYND/`:
- overnight_research (02:00) — deep research on one backlog topic -> knowledge-base/research/
- morning_briefing (07:00) — news + 3 priorities -> briefings/
- daily_execution (09:00) — act on top-3 tasks -> logs/
- weekly_review (Sun 21:00) — shipped/stalled/next -> reviews/
- monthly_strategic_review (1st 10:00) — scale/kill/leverage -> reviews/

## 6. Autonomous Opportunity Discovery
- overnight_research maintains `research_backlog.md` (opportunities + signals).
- monthly_strategic_review scores opportunities; top 1 becomes next quarter's bet.
- Founder ratifies; agents draft validation tests.

## 7. Error Recovery
- On tool failure: report honestly, try one alternative (pkg mgr / approach), then stop and ask.
- Never substitute fabricated output for a failed real call.
- Cron jobs wrap work in try/except and write a `STATUS: blocked (reason)` line so the founder sees failure in files, not silent success.

## 8. Experiment Tracking
- `experiments/` dir: each experiment = markdown with hypothesis, method, metric, result, decision.
- Weekly review rolls experiment outcomes into lessons.

## 9. Project Health Monitoring
- A `health.md` per project: 5 signals (momentum, revenue, engagement, blockers, next action) scored 1-5.
- Monthly review trends the scores.

## 10. Goal Tracking
- `goals.md`: annual objectives -> quarterly key results -> weekly commitments.
- Morning briefing re-states the week's commitment; daily execution advances it.

## 11. Decision Framework
- For any initiative: Leverage = (impact × reversibility) / effort. Act fast when reversible.
- Kill rule: if no validated signal in 2 weeks and leverage < 5, cut or pause.
- Default to shipping a small real thing over a perfect plan.

## 12. Priority System
1. Revenue-generating client work (committed).
2. Highest-leverage founder task of the day (from goals KR).
3. Community momentum (content/engagement that compounds).
4. Backlog research/experimentation.
Agents never reorder 1 without founder ok.
