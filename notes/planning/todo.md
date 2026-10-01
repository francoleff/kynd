# KYND TODO (quick capture)

## DONE / AUTOMATED (no manual work needed)
- Discord onboarding automation — EXISTS in bot (`onboard_scheduler`, DMs day 1/3/7). Idle until members join (distribution bottleneck).
- Resource drop — AUTOMATED weekly from KYND_Library.xlsx (monitor_resources_xlsx.py, LIVE). No manual xlsx refresh.
- Newsletter/content cuts — CONTENT ENGINE generates all 4 cuts from one --topic (content-engine/engine.py). No manual rewrite.
- Dashboard metrics — sync_dashboard.py regenerates metrics + flags drift. Run on demand.
- Kynd-os + workspace/kynd — under LOCAL GIT (recovery baseline). kp-backup script ready (hourly launchd not installed).

## NEEDS FRANCO'S DECISION / APPROVAL (consequential)
- Publish the markdown Kynd Library (build_site.py → _site/ ready; needs deploy approval).
- Install hourly kp-backup launchd job (protects live bot state).
- Retire broken Bing competitor daemon (retire-broken-monitors.sh ready; RSS replacement on-demand).
- Pin or drop the 3 drift-blocked gateway cron jobs (f362/4490/6377) — spend decision.

## OPEN WORK (real)
- Integrate the 6 strategy-agent outputs into KYND/ docs (low value, was deferred).
- Decide premium offer price + package (business decision, not automation).
- Distribution: the actual bottleneck is reaching members, not tooling.
