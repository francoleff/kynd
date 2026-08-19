# 7. The Prompt Vault

Prompts by job . Copy-paste ready . Adjust names and paths to your setup .

Two kinds : **From the docs** . Taken from official docs or examples . **Ours** . Built on verified features but not machine-tested . The vault is a starting point , not magic .

- **Research:**
  - *From the docs :*
    ```
    Summarize this repository in 5 bullets and tell me what the main entrypoint is .
    ```
    ```
    Search for the latest news about AI agents and open source LLMs . Summarize the top 3 stories in a concise briefing format with links .
    ```
  - *Ours :*
    ```
    Research <topic> . Prefer primary sources (official docs , papers , repos) . For each key claim include the source URL . Mark anything you can't verify [UNVERIFIED] . Output : summary , key facts , sources , open questions .
    ```
    ```
    Find the current pricing and free tiers for <tool> . Compare at least 3 sources and flag where they disagree .
    ```
    ```
    What changed in <field> in the last 30 days ? Search for announcements and releases , not tutorials . Give me a dated changelog with links .
    ```

- **Planning:**
  - *Ours :*
    ```
    I want to <goal> . Make a plan : scope , steps (each with an owner : me / you / a subagent) , risks with fallbacks , and a first action . Keep it under 300 words .
    ```
    ```
    Break <big task> into parallel workstreams . For each : goal , inputs needed , expected output , and how we verify it . Flag anything that must happen sequentially .
    ```
  - *From the docs :*
    ```
    /goal <text> : set a standing goal Hermes keeps working toward across turns .
    ```

- **Execution:**
  - *From the docs :*
    ```
    Check my current directory and tell me what looks like the main project file .
    ```
  - *Ours :*
    ```
    Do <task> now . Follow my task template : state what you'll do , do it , then report what changed and how I can verify it .
    ```
    ```
    Take the plan in <file> and execute step 1 . Ask before touching anything outside <folder> .
    ```

- **Analysis:**
  - *Ours :*
    ```
    Analyze <data/file> . Summarize the signal , call out anomalies , and rank the top 3 insights by actionability . Be specific about what you looked at .
    ```
    ```
    Compare <option A> vs <option B> for <situation> . Table format : cost , effort , risk , best use case . Then give a recommendation with reasoning .
    ```
    ```
    Read <document> and extract every decision , deadline , and open question into a structured list . Quote exact text where it matters .
    ```

- **QA:**
  - *From the docs :*
    ```
    Find at least 5 recent articles from the past 24 hours . Summarize the top 3 most important stories . For each : clear headline , 2-sentence summary , source URL . End with a total story count .
    ```
  - *Ours :*
    ```
    QA my output in <file> against the spec in <AGENTS.md> . Check accuracy (spot-check links) , completeness , format , and fabrication . Report a verdict : ship / fix these items / redo .
    ```
    ```
    Red-team my <system/plan> : list the 5 most likely failure points , what each would cost , and the cheapest mitigation .
    ```

- **Debugging:**
  - *Ours :*
    ```
    Here's the error (paste it) . Find the root cause . Show me the relevant docs or references for the fix , then propose the minimal change .
    ```
    ```
    Debug <behavior> : state your hypothesis , run one diagnostic , and only change one thing at a time . Tell me what you tried and what it proved .
    ```

- **Delegation:**
  - *From the docs :*
    ```
    Research topic A . Focus on recent primary sources .
    ```
    ```
    delegate_task(tasks=[{"goal": "Research topic A", "context": "..."}, {"goal": "Research topic B", "context": "..."}])
    ```
  - *Ours :*
    ```
    Spawn a subagent to <isolated task> . Give it the exact inputs and the exact output format . It must not modify <protected paths> .
    ```

- **Automation:**
  - *From the docs :*
    ```
    /cron add 30m "Remind me to check the build"
    ```
    ```
    /cron add "every 2h" "Check server status"
    ```
    ```
    /cron add "0 8 * * *" "Search the web for the latest news about AI agents and open source LLMs . Find at least 5 recent articles from the past 24 hours . Summarize the top 3 most important stories in a concise daily briefing format . For each story include : a clear headline , a 2-sentence summary , and the source URL . Use a friendly , professional tone . Format with emoji bullet points and end with a total story count ."
    ```
  - *Ours :*
    ```
    /cron add "0 9 * * 1" "Run the research-brief skill for each topic in topics.md . Save briefs to briefs/ following AGENTS.md . Deliver: local ."
    ```

- **Documentation:**
  - *Ours :*
    ```
    Document <codebase/feature> for a beginner : what it is , how to install and run it , one working example , and the 3 most common mistakes .
    ```
    ```
    Turn this conversation into a how-to guide : exact steps , exact commands , expected output . Cut everything that isn't needed to reproduce the result .
    ```
    ```
    Write a changelog entry for <change> : what changed , why , migration steps if any , and what to verify after updating .
    ```

- **Business:**
  - *Ours :*
    ```
    Draft <outreach/email/social post> for <audience> . Plain language , one CTA , no hype . Give me 3 variations with different openings .
    ```
    ```
    Build me a weekly ops report : pull <metrics/status> , flag anomalies vs last week , and draft the 3 decisions that need my attention .
    ```
    ```
    My client said <quote> . Draft a calm , specific reply that restates the issue , offers a fix or timeline , and asks one clear question .
    ```

- **Why some prompts are long:**
  - Be specific : name files , paths , formats , and what "done" looks like .
  - Self-contained for cron : scheduled jobs have no conversation memory . Everything the job needs must be in the prompt .
  - One job per prompt : "research X and write a brief" beats "help me with my project ."
  - Iterate : prompt → check output → refine .

**NEXT →** [8 : TROUBLESHOOTING](08-troubleshooting.md)
