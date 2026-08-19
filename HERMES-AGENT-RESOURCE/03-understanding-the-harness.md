# 3. The Harness: Tools, Memory & Connections

Fifteen minutes . Only the concepts you actually touch in the first weeks .


- **The one idea that matters:** Hermes runs a loop :
  - read context → think → pick a tool → act → observe → repeat
  - Until your request is done .

  Everything you control feeds the first step : your system prompt , context files , the conversation , memory , skills . That's why being specific in your prompts works . It's the only way you steer the loop .

- **Tools and toolsets:** 60+ built-in abilities : web search , file read/write , terminal , browser , image generation , code execution . Grouped into toolsets : web , terminal , file , browser , vision , memory , delegation , cron ... You rarely call a tool by name . The agent picks them . You just keep the toolset on :

  ```bash
  hermes tools                # see and toggle tool groups
  ```

  The main tools you'll see in action :
  - Web : `web_search` , `web_extract`
  - Terminal and files : `terminal` , `process` , `read_file` , `patch`
  - Browser : `browser_navigate` , `browser_snapshot` , `browser_vision`
  - Media : `vision_analyze` , `image_generate` , `text_to_speech`
  - Orchestration : `todo` , `clarify` , `execute_code` , `delegate_task`
  - Memory and recall : `memory` , `session_search`
  - Automation : `cronjob`

- **Terminal backends : where commands run** . The sandbox where the agent executes shell commands .
  - `local` : your machine . Default . Fine for learning .
  - `docker` : isolated container .
  - `ssh` : another machine .
  - `modal` / `daytona` : serverless cloud .
  - `singularity` , `vercel_sandbox` : more options .

  You don't touch this at first . Local is fine . Docker becomes useful when you let the agent do riskier things (section 6) .

- **Skills : how it learns** . A skill is a document , `SKILL.md` , that teaches Hermes a multi-step workflow . It creates skills on its own after complex tasks and improves them while it works . They're portable : the `agentskills.io` open standard . Where : `~/.hermes/skills/` , plus the Skills Hub for community skills . In chat :

  ```
  /skills                     # browse installed + hub skills
  /plan Make a content calendar   # every installed skill is a slash command
  ```

  Install from the hub :

  ```bash
  hermes skills install official/research/arxiv
  ```

  That "learns from experience" part is the point . Watch it happen after a hard task .

- **Memory : facts that persist** . Your preferences . Your setup . Lessons learned . Where it lives :
  - `~/.hermes/memories/MEMORY.md` . The agent's notes . ~2,200 chars max .
  - `~/.hermes/memories/USER.md` . Your profile . ~1,375 chars max .
  - `~/.hermes/state.db` . Full history , searchable .

  Nothing to configure . The agent writes memory itself . You'll see it note things like "user prefers bullet points" . Tell it directly : "Remember : I always want sources included ." To search old chats , it uses `session_search` . Memory vs skills : memory is facts (who you are) . Skills are procedures (how to do a workflow) .

- **Context files : how you shape every conversation** . Markdown files injected into every session automatically . Your rules . Your conventions . Your tone .
  - `SOUL.md` at `~/.hermes/SOUL.md` . Your agent's global identity and voice . Only this location is read .
  - `.hermes.md` / `HERMES.md` in the project root . Project instructions . Highest priority .
  - `AGENTS.md` in the project root . Conventions , architecture , rules .
  - `CLAUDE.md` , `.cursorrules` . Imported from other AI tools you may use .

  The habit that pays the most : put an `AGENTS.md` in each project folder . Template in section 5 .

- **Personality:** The agent's default voice . Lives at `~/.hermes/SOUL.md` .

  ```
  /personality helpful       # built-ins : helpful , concise , technical , teacher , pirate ...
  /personality none          # back to default
  ```

  Custom personalities live in `config.yaml` under `agent.personalities` .

- **Sessions:** Every conversation is a session , saved automatically to SQLite .

  ```bash
  hermes                    # new session
  hermes --continue         # resume the most recent (-c works too)
  hermes sessions list      # browse past sessions
  ```

  In chat : `/new` (fresh) , `/title <name>` , `/sessions` (picker) . Export with `hermes sessions export` .

- **Security : read this before letting it do things** . Before dangerous shell commands , Hermes asks . The prompt :

  `[o]nce | [s]ession | [a]lways | [d]eny`

  Modes in `config.yaml` → `approvals.mode` :
  - `smart` . Default . Auto-approves safe , asks on risky .
  - `manual` . Asks more .
  - `off` . No approval . You've been warned .

  Some commands are hard-blocked and cannot be approved : `rm -rf /` , fork bombs . By design . Checkpoints : optional snapshots before destructive operations . Enable them :

  ```yaml
  checkpoints:
    enabled: true
  ```

  Undo with `/rollback` . My rules : use `once` or `session` when approving , never `always` . Never run `/yolo` (bypasses approvals) on your main machine .

- **Delegation : parallel subagents** . `delegate_task` spawns isolated subagents with their own context . They work in parallel and return summaries . Use it for parallel research or multi-file edits without flooding the main conversation . You'll use this in Build 6 . Watch `/agents` in the TUI to see live subagent trees .

- **Cron : scheduled automation** . Natural-language scheduling , delivered anywhere .

  ```
  /cron add "every 2h" "Check server status"
  /cron add "0 8 * * *" "Search the web for latest AI agent news and write a briefing to a file"
  /cron list
  /cron remove <id>
  ```

  Delivery : `local` (files in `~/.hermes/cron/output/` , default in CLI) , `telegram` , `discord` , `email` ... One gotcha : cron jobs run in fresh sessions with no memory . The prompt must be self-contained .

- **MCP : plug in external tools** . MCP (Model Context Protocol) connects external tool servers , databases , GitHub , internal APIs , as new tools . Later : `hermes mcp` , or entries in `config.yaml` under `mcp_servers` . Example :

  ```yaml
  mcp_servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
  ```

- **The gateway : talk to it from anywhere** . One process connects your agent to 20+ messaging platforms , Telegram , Discord , Slack , WhatsApp , Signal , Email ...

  ```bash
  hermes gateway          # run in foreground
  hermes gateway setup    # configure a platform
  ```

  Safety : access is protected by allowlists or a DM pairing code . Never set `GATEWAY_ALLOW_ALL_USERS=true` on an agent with terminal access .

- **Cheat sheet:**
  - Change its voice → `SOUL.md` or `/personality`
  - Teach it your project's rules → `AGENTS.md` in the project folder
  - Teach it a repeatable workflow → a skill
  - Make it remember facts about you → tell it explicitly
  - Schedule something → `/cron add`
  - Run things in parallel → `delegate_task`
  - Undo damage → `/rollback` (enable checkpoints first)
  - Reach it from your phone → gateway (Telegram / Discord)
  - Add new abilities → MCP server

**NEXT →** [4 : BUILD 1: THE RESEARCH BRIEF AGENT](04-build-your-first-agent.md)
