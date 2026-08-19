# 6. Practical Agent Builds

Build 2 is fully built . Builds 3-6 are outlined . Each one maps only to verified features , and each gets a full build when it ships .

An outline is not a promise . If it isn't possible with the current verified capabilities , it isn't here .

- **Build 2 : Research Agent (COMPLETE)** . Easy-to-medium . Needs sections 1-4 and web search enabled . The section 4 agent , expanded into a tool you actually rely on .
  - **What it does:**
    - Tracks a topic list (`topics.md`)
    - Researches on demand or on a schedule , and writes briefs
    - Keeps a running brief archive you can search
    - Marks unverifiable claims instead of inventing them
  - **Setup:**

    ```bash
    mkdir -p ~/kynd/research-agent/briefs
    cd ~/kynd/research-agent
    ```

    1. `AGENTS.md` . Copy from [section 4 , File 1](04-build-your-first-agent.md#file-1--agentsmd-in-kyndresearch-agent) .
    2. `SOUL.md` . Copy from [section 4 , File 2](04-build-your-first-agent.md#file-2--soulmd-global-personality--one-time) (or Asset 1 in section 5) .
    3. `topics.md` . Your topic list .
    4. Create the skill : in chat , after a successful brief :

    ```
    Create a skill from this research-brief workflow so I can run it on any topic.
    ```

    5. Schedule it (optional) :

    ```
    /cron add "0 9 * * 1" "Run the research-brief skill for each topic in topics.md.
    Save briefs to briefs/ following AGENTS.md. Deliver: local."
    ```

  - **Daily use:**

    ```bash
    cd ~/kynd/research-agent && hermes
    /research-brief "vector databases in 2026"
    ```

  - **Upgrades (when you're ready):**
    - Briefings to your phone : connect Telegram or Discord (gateway) , then `deliver: telegram` .
    - Deeper research : teach it `delegate_task` to research 3 subtopics in parallel and merge the results .
    - Cost control : `/usage` to see spend per session . Delegate subtasks to a cheaper model via `delegation.model` in `config.yaml` .
  - **Release gate:**
    - [ ] Skill runs from a fresh chat on a new topic
    - [ ] Briefs land in `briefs/` with correct naming and format
    - [ ] 2+ source links spot-checked , no fabrications
    - [ ] Unverifiable claims marked `[UNVERIFIED]`
    - [ ] Cron delivery works (if configured)
    - [ ] Output is useful , not filler

- **Build 3 : Personal Assistant (NEXT)** . Medium . Gateway , memory , personality , cron . Your Research Agent , upgraded into something you text from your phone . Reminders . Briefings . Inbox triage .
  - **Build path (all verified features):**
    1. Set up the gateway : `hermes gateway setup` → Telegram or Discord bot .
    2. Secure it : allowlist your user ID (never `GATEWAY_ALLOW_ALL_USERS=true`) or use DM pairing .
    3. Give it memory : tell it your preferences , routines , and standing instructions .
    4. Schedule daily briefings and reminders via `/cron add` with `deliver: telegram` .
  - **Release gate:** "I can text my agent and get a useful reply , and it runs my Monday briefing unattended ."

- **Build 4 : Content System (NEXT)** . Medium . Skills , batch processing , templates . An agent pipeline that turns raw ideas into structured content drafts , essays → threads → posts , using skills and your style rules .
  - **Build path (all verified features):**
    1. Write a "content style" skill (SKILL.md) that encodes your voice rules and formats .
    2. Create a content workflow AGENTS.md (inputs → drafts → QA pass) .
    3. Use cron and delegation for batch processing of ideas .
  - **Release gate:** "I feed it 5 ideas ; it returns formatted drafts matching my voice with a QA pass ."

- **Build 5 : Business Operations Agent (NEXT)** . Medium-hard . Cron , delegation , checkpoints , MCP . Scheduled , delegated operations , daily status reports , weekly audits , invoice and CRM touchpoints .
  - **Build path (all verified features):**
    1. Enable checkpoints (`checkpoints.enabled: true`) before it touches real files .
    2. Stand up cron jobs for reports and backups with `deliver: local` + a messaging channel .
    3. Add MCP servers for real systems (database , CRM , GitHub) via `hermes mcp` .
    4. Route parallel subtasks through `delegate_task` with a cheaper `delegation.model` .
  - **Release gate:** "It runs my Monday ops report from real data , unattended , and I trust the output enough to forward it ."

- **Build 6 : Multi-Agent Workflow (NEXT)** . Hard . Delegation , kanban , goals . Several specialized agents , researcher , writer , QA , coordinated on one task board .
  - **Build path (all verified features):**
    1. Multiple profiles , each with its own SOUL.md / AGENTS.md .
    2. `delegate_task` for parallel workstreams .
    3. The SQLite-backed kanban board to coordinate tasks across profiles .
    4. `/goal` for standing objectives the agent keeps working toward .
  - **Release gate:** "I define a project ; agents divide it , work in parallel , and I review the merged result ."

- **The matrix:**

  | # | Build | Difficulty | Core features | Status |
  |---|---|---|---|---|
  | 1 | Research Brief Agent | Easy | AGENTS.md , skill , cron | COMPLETE (section 4) |
  | 2 | Research Agent | Easy-Med | Skills , cron , web | COMPLETE |
  | 3 | Personal Assistant | Medium | Gateway , memory | NEXT |
  | 4 | Content System | Medium | Skills , batch | NEXT |
  | 5 | Business Operations | Med-Hard | Cron , MCP , checkpoints | NEXT |
  | 6 | Multi-Agent Workflow | Hard | Delegation , kanban | NEXT |

**NEXT →** [7 : THE PROMPT VAULT](07-prompt-vault.md)
