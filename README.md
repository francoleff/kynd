# kynd

Working repo for KYND, a free community and library for solo agentic-AI builders.

| Folder | What it is |
|--------|------------|
| `content-engine/` | Python pipeline that turns one topic into platform-ready drafts (`engine.py`, `run_scheduled.py`, `post.py`). `com.kynd.content-engine.plist` schedules it on macOS. |
| `kynd-library/` | Markdown knowledge base (foundation, build, playbooks, case studies, and more). `build_site.py` builds it into `_site/`; `check-links.mjs` checks links. |
| `kynd-site/` | Static website: landing page, library, first-build guide. Deployed on Netlify. |
| `notion-push/` | Node script that pushes library content to Notion (`push.js`). |
| `notes/` | Operating notes. `planning/` (goals, roadmap, tasks, health, todo), `reference/` (brand, strategy, Hermes design), `briefings/`, `logs/`, `knowledge-base/`, `outreach/`, `landing/`, `workflows/`. |
| `SKILL.md` | Dan Koe writing-style skill used by the content engine. |

The runtime code lives outside this repo, in `~/workspace/kynd-runtime`.
