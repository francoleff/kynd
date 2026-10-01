#!/usr/bin/env python3
"""
KYND posting engine v1 — one topic -> platform-ready drafts + safe dispatch.

No external calls by default. Generates tailored drafts per platform from a
single --topic, and dispatches ONLY when --go is passed AND the platform token
is present in env. This keeps it honest: it will never post unverified or to
accounts you haven't authenticated.

Usage:
  python3 post.py --topic "AI automation for busy owners"          # show drafts
  python3 post.py --topic "..." --platforms linkedin,x,threads     # show those
  python3 post.py --topic "..." --go                               # real dispatch
"""
import argparse, os, sys

PLATFORMS = {
    "linkedin": {"env": "LINKEDIN_TOKEN", "label": "LinkedIn", "limit": 3000,
                 "tone": "professional, teach one concrete win"},
    "x":        {"env": "X_TOKEN", "label": "X/Twitter", "limit": 280,
                 "tone": "punchy, thread-ready hook"},
    "threads":  {"env": "THREADS_TOKEN", "label": "Threads", "limit": 500,
                 "tone": "casual, one sharp take"},
    "bluesky":  {"env": "BLUESKY_TOKEN", "label": "Bluesky", "limit": 300,
                 "tone": "plain, no hype"},
    "reddit":   {"env": "REDDIT_TOKEN", "label": "Reddit", "limit": 40000,
                 "tone": "subreddit-fit, value first"},
    "facebook": {"env": "FB_TOKEN", "label": "Facebook", "limit": 63206,
                 "tone": "friendly, story-led"},
    "substack": {"env": "SUBSTACK_TOKEN", "label": "Substack", "limit": 0,
                 "tone": "long-form essay"},
}

def draft(platform, topic):
    cfg = PLATFORMS[platform]
    lim = cfg["limit"]
    if platform == "linkedin":
        t = (f"{topic}\n\nMost owners don't have a talent problem. They have a "
             f"repeat-loop problem. The work that eats your week is the same 12 "
             f"tasks wearing different clothes.\n\nPick one. Automate it this "
             f"week. The rest compounding from there.\n\nWhat's the first task "
             f"you'd hand off?")
    elif platform == "x":
        t = (f"{topic}\n\nThe owners winning with AI aren't using 50 tools.\n"
             f"They picked one repeat problem and killed it.\n\nStart smaller "
             f"than feels stupid.")
    elif platform == "threads":
        t = (f"{topic}\n\nHot take: your 'busy' is mostly the same task 40 times.\n"
             f"Automate the task, not the vibe.")
    elif platform == "bluesky":
        t = (f"{topic}. The highest-leverage move for a small business is "
             f"automating the one task you do every single day.")
    elif platform == "reddit":
        t = (f"Title: {topic} — what actually worked for you?\n\nBody: I keep "
             f"seeing owners burn out on repeat admin. Curious what one "
             f"automation genuinely moved the needle for your business, and "
             f"what was overhyped.")
    elif platform == "facebook":
        t = (f"{topic}\n\nQuick one: last month I watched a owner lose ~10 hours "
             f"to the same invoice dance. We scripted it. Got the time back.\n\n"
             f"If you run something small, what's your version of that task?")
    else:  # substack
        t = (f"# {topic}\n\n(essay body — expand from the LinkedIn draft; this "
             f"is the long-form cut)")
    if lim and len(t) > lim:
        t = t[:lim-3].rstrip() + "..."
    return t

def dispatch(platform, text):
    """Post `text` to `platform`. Returns (ok, msg)."""
    cfg = PLATFORMS[platform]
    tok = os.environ.get(cfg["env"])
    if not tok:
        return False, f"{cfg['label']}: no token in env ({cfg['env']})"
    # TODO: real API call with `tok` and `text`. Flip to live once verified.
    return False, f"{cfg['label']}: client not wired yet (token present)"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--platforms", default="linkedin,x,threads,bluesky,reddit,facebook,substack")
    ap.add_argument("--go", action="store_true", help="real dispatch (needs tokens)")
    a = ap.parse_args()
    targets = [p.strip() for p in a.platforms.split(",") if p.strip() in PLATFORMS]
    if not targets:
        print("unknown platform in:", a.platforms); sys.exit(1)
    print(f"=== KYND post drafts for: {a.topic!r} ===\n")
    for p in targets:
        d = draft(p, a.topic)
        print(f"--- {PLATFORMS[p]['label']} ({len(d)} chars) ---")
        print(d)
        if a.go:
            ok, msg = dispatch(p, d)
            print(f"  -> {'OK' if ok else 'SKIP'} | {msg}")
        print()
    if not a.go:
        print("(dry-run: add --go to dispatch; tokens required per platform)")

if __name__ == "__main__":
    main()
