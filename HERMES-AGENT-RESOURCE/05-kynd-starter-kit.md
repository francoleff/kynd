# 5. Persona, Identity & The Starter Kit

Copy-paste assets that make every future agent faster to build . Only assets that map to a real Hermes feature made the cut . Nothing decorative . Five minutes each . Grab what you need .

Feature support is verified against the official docs . The templates themselves are ours . Starting points , not gospel . Ready-to-copy files live in [`ASSETS/`](ASSETS/) . Same content , one file each . Copy what's inside the fence , not the wrapper text .

- **The workspace convention:** One project , one folder , one `AGENTS.md` . The habit that makes agents reliable .

  ```
  ~/kynd/
    research-agent/      → AGENTS.md + briefs/        (section 4 / Build 1)
    personal-assistant/  → AGENTS.md + gateway setup   (Build 3 , later)
    content-system/      → AGENTS.md + skills/         (Build 4 , later)
  ```

  Folder names are examples . Pick your own . The rule : one project , one folder , one AGENTS.md . Memory : you don't create it . The agent does . `~/.hermes/memories/MEMORY.md` (agent notes) and `USER.md` (your profile) , each with hard character limits . Tell the agent your preferences explicitly . "Remember : always include sources" . It writes them down .

- **Asset 1 : Starter system prompt (SOUL.md)** . Your agent's permanent identity and voice . Lives at `~/.hermes/SOUL.md` .

  ```markdown
  # SOUL.md

  You are Kynd, a sharp, honest, practical AI assistant.
  - Plain language. No fluff, no hype, no filler.
  - You verify before you state. You say "I don't know" when you don't know.
  - You write for a reader who wants to DO something with the information.
  - Every factual claim is backed by a source or marked unverified.
  - You ask one clarifying question when the request is ambiguous, then proceed.
  ```

  Usage : edit it to fit your voice . Deleting the file restores the default personality . Session-only alternative : `/personality` presets .

- **Asset 2 : Agent instructions (AGENTS.md)** . Per-project rules injected into every conversation . Lives in the project root .

  ```markdown
  # <Project Name>

  ## Role
  You are <role>. You produce <output type>, not essays.

  ## Working directory
  - <where outputs go, naming convention>

  ## Rules
  1. <rule 1 : e.g., "verify claims before stating them">
  2. <rule 2 : e.g., "never invent sources">
  3. <rule 3 : e.g., "ask before destructive commands">

  ## Output format (every deliverable, exactly)
  # <Title>
  ## Summary
  ## Details
  ## Sources

  ## Done looks like
  - <checklist of what "finished" means>
  ```

- **Asset 3 : Skill template (SKILL.md)** . A repeatable workflow the agent can run on demand . Lives at `~/.hermes/skills/<category>/<skill-name>/SKILL.md` .

  ```markdown
  ---
  name: <skill-name>
  description: Brief description of what this skill does
  version: 1.0.0
  metadata:
    hermes:
      tags: [<tag1>, <tag2>]
      category: <category>
  ---

  # <Skill Title>

  ## When to Use
  Use this skill when the user asks to <trigger condition>.

  ## Procedure
  1. <step 1>
  2. <step 2>
  3. <step 3>

  ## Pitfalls
  - Common failure: <description>. Fix: <solution>

  ## Verification
  Run <check> to confirm the result is correct.
  ```

  Usage : once saved , the skill name becomes a slash command : `/research-brief "topic"` . Write it by hand , or ask the agent to create it for you .

- **Asset 4 : Task template** . One small task framed so the AI can run with it . The Kynd method in a box .

  ```markdown
  TASK: <one sentence : what to do>
  DONE WHEN: <what success looks like, checkable>
  CONTEXT: <what the agent needs to know>
  - <key fact 1>
  - <key fact 2>
  CONSTRAINTS: <what not to do>
  - <constraint 1>
  DELIVERABLE: <file / message / format>
  VERIFY: <how we'll check it worked>
  ```

- **Asset 5 : Planning template** . Turns a vague goal into a plan the agent can execute . Pairs with `/goal` for standing work .

  ```markdown
  GOAL: <what you want, in one sentence>
  DEADLINE: <date or "none">
  SCOPE: <what's included : and what's explicitly NOT>
  STEPS:
  1. <step : with owner (you / agent / subagent)>
  2. <step>
  RISKS: <what could break, and the fallback>
  FIRST ACTION: <the one thing to do now>
  ```

- **Asset 6 : Research template** . A research brief spec . Pairs with the Build 1 agent (section 4) .

  ```markdown
  RESEARCH: <topic>
  QUESTIONS TO ANSWER:
  1. <question>
  2. <question>
  SOURCES: <primary | mixed | any>
  - <source preference, e.g., "official docs first">
  RULES:
  - Only claims you can attribute to a source you read.
  - Mark unverifiable claims [UNVERIFIED].
  OUTPUT: <file or format>
  FORMAT: <e.g., "summary + key facts + sources + open questions">
  ```

- **Asset 7 : QA template** . Check an agent's output before you trust it . Use it on everything the agent produces .

  ```markdown
  OUTPUT CHECKED: <what was produced>
  ACCURACY: <did you spot-check claims? how many links followed?>
  COMPLETENESS: <does it answer the original task?>
  FORMAT: <does it match the spec?>
  FABRICATIONS: <any invented facts/quotes/sources? : list them>
  VERDICT: <ship / fix these items / redo>
  ```

- **Asset 8 : Autonomous execution template** . Hand a bounded autonomous task to the agent , with guardrails .

  ```markdown
  EXECUTE: <task>
  AUTONOMY LEVEL: <full | ask before destructive | ask before external actions>
  APPROVAL RULES:
  - Never run <specific dangerous commands> without asking.
  - Never modify <protected files/folders>.
  REPORT BACK: <what the final message must include>
  ROLLBACK: <checkpoints on? what's the undo path?>
  ```

- **Grab-and-go:**

  | Asset | File in ASSETS/ | Maps to feature |
  |---|---|---|
  | Starter system prompt | `SOUL.md` | Personality |
  | Agent instructions | `AGENTS.md` | Context files |
  | Skill template | `SKILL-template.md` | Skills system |
  | Task template | `task-template.md` | Prompting |
  | Planning template | `planning-template.md` | `/goal` , planning |
  | Research template | `research-template.md` | Build 1 workflow |
  | QA template | `qa-template.md` | QA discipline |
  | Autonomous execution template | `autonomous-execution-template.md` | Approvals / security |

**NEXT →** [6 : PRACTICAL AGENT BUILDS](06-real-projects.md)
