# Continuous AI Tool Discovery System

Goal: never let the KYND library go stale. New AI tools ship weekly; we capture the
ones worth teaching before they hit mainstream.

## Sources (weekly scan)
- Product Hunt "AI" category (https://www.producthunt.com/topics/artificial-intelligence)
- Hacker News "Show HN" + "AI" (https://news.ycombinator.com)
- GitHub Trending (https://github.com/trending?since=weekly)
- Latent Space / HF posts
- X accounts: @swyx, @simonw, @rohanpaul, @omarsar0, agent-framework authors

## Process (automated weekly)
1. Weekly agent scans sources, extracts candidate tools (name, URL, one-line what).
2. Scores each: Novelty (1-5) | Usefulness to agentic builder (1-5) | Maturity (1-5).
3. Score >=10 -> add to `Emerging 20` sheet of KYND_Library.xlsx (bump lowest out).
4. Score >=13 after 1 month of monitoring -> promote to `Top 50 Tools`.
5. Log everything to knowledge-base/research/<date>-tool-watch.md.

## Output
- KYND_Library.xlsx (Emerging 20 + Top 50)
- knowledge-base/research/ tool-watch notes

## Cron
`Kynd Weekly Tool Scan` (see cronjob) runs Sundays, writes candidates to the sheet + log.
