#!/usr/bin/env python3
"""
Kynd Content Engine — deterministic 1-pillar-4-cuts generator.

Replaces the manual per-platform rewrite Franco does every week (task T-001).
Feed it ONE topic + optional remix seed, get all four platform cuts in his
enforced voice (spaced punctuation, hook->enemy->advantage->CTA, one CTA each).

Local only. Writes to ../generated/<topic-slug>/ — never posts, never deploys.

Usage:
    python3 engine.py --topic "why beginners stall with AI" --cta-link https://join-kynd.netlify.app
    python3 engine.py --topic "..." --remix "Most people adopt a routine they repeat until 80"
    python3 engine.py --topic "..." --dry-run        # print, no files
    python3 engine.py --list-topics                   # show what's been generated

Voice rules enforced (from kynd-voice skill):
- Spaced punctuation: "word ," "word ." "word ?" "word !"
- No banned bio framing (18, dropout, broke, no degree ...)
- No banned words (ship, guru, building in public, annoying task)
- Plain, blunt, single-sentence paragraphs, heavy whitespace
- One CTA per platform
"""
import argparse
import re
import json
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
GEN = HERE / "generated"

BANNED_BIO = ["18", "18-year-old", "dropped out", "dropout", "no degree",
              "no savings", "broke", "no network", "just shipping"]
BANNED_WORDS = ["ship", "shipping", "guru", "annoying task", "building in public"]


def spaced(text: str) -> str:
    """Enforce Franco's spaced punctuation: mark gets its own space, lowercased."""
    # Normalize any existing spacing around marks first.
    text = re.sub(r"\s*([,.;?!])\s*", r" \1 ", text)
    # Collapse runs of spaces, then fix double-spaces at sentence starts.
    text = re.sub(r"[ ]{2,}", " ", text)
    # Capitalize after . ? ! (start of new sentence), but keep list markers "1." intact.
    text = re.sub(r"([.?!]) ([a-z])", lambda m: m.group(1) + " " + m.group(2).upper(), text)
    # Capitalize first char.
    text = text[0].upper() + text[1:] if text else text
    return text.strip()


def guard(text: str) -> str:
    low = text.lower()
    for b in BANNED_BIO + BANNED_WORDS:
        if b in low:
            raise SystemExit(f"VOICE GUARD TRIPPED: banned token '{b}' in output. Fix the seed/source.")
    return text


def build_cuts(topic: str, cta_link: str, remix: str = None):
    hook = ("Every AI community is either people selling courses or people flexing "
            "wins they can't explain . Neither helped me actually build .")
    enemy = "You're told you need credentials first . A certificate . A following . A reason to be allowed ."
    advantage = ("Kynd is a free place to build with AI agents . Beginners welcome . "
                 "Especially beginners . People at every level help each other . "
                 "Nobody acts like they've figured it all out .")
    remix_line = ""
    if remix:
        remix_line = f"\nOne line stays with me : \"{remix}\"\n"

    topic_sent = spaced(topic.rstrip(". ")) + " ."

    # SUBSTACK — the pillar (deepest).
    substack = f"""# {spaced('Kynd : ' + topic)}

I've been building with AI agents for a while now .

The hard part was never the tech . It was doing it alone .{remix_line}
{topic_sent} Most people stall before they start because the bar looks impossible . It isn't .

Here's what actually moves you forward .

Name one small task you do a lot . The one that eats time . Explain it to a friend in plain words . Then talk to the AI like a person . Tell it what you want . When it gets it wrong , say what failed and try again . Three rounds and it works .

That's the whole method . No courses . No gatekeeping . No fake screenshots .

Inside Kynd , people at every level help each other . Someone explains a thing in plain words . Someone else shares what they made . I'm there every day , figuring it out like everyone else .

If you've been curious about AI agents but didn't know where to start , this is the start .

Join free : {cta_link}

Franco
"""

    # X THREAD — the reach engine.
    x_thread = f"""# X Thread . {spaced(topic)}

1. {hook}
2. So I built the one I wanted . It's called Kynd .
3. No courses . No gatekeeping . No fake screenshots .
4. {spaced('Here is the part nobody tells you : ' + topic)} .
5. {advantage}
6. Know yourself , build with intention .
7. Join free : {cta_link}
"""

    # LINKEDIN — authority cut.
    no_cred = spaced("Most teams treat AI like a credential they have to earn first . It isn't .")
    linkedin = f"""# LinkedIn . {spaced(topic)}

{no_cred}

{topic_sent} The people getting ahead aren't the most technical . They're the ones who picked one annoying problem and solved it in the open .

Kynd is a free community for people learning to build with AI agents . Beginners welcome . People at every level help each other . No courses , no gatekeeping , no fake screenshots .

If you're building or want to start , comment and I'll send the invite .

{cta_link}
"""

    # REDDIT — no links, value first, trust.
    reddit = f"""# Reddit . {spaced(topic)}

Title : I got tired of AI communities being all courses and flexing , so I made a free one for actual beginners .

I've been building with AI agents for a while . The hard part was never the tech . It was doing it alone .

Every community I found was one of two things . People selling courses . Or people flexing wins they couldn't explain . Neither helped me actually build .

So I started Kynd . A free place where people at every level help each other . No courses . No gatekeeping . No fake screenshots .

{topic_sent} If that's you , the door is open . Happy to answer anything about getting started .
"""

    cuts = {
        "substack": guard(substack),
        "x_thread": guard(x_thread),
        "linkedin": guard(linkedin),
        "reddit": guard(reddit),
    }
    return cuts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", help="The pillar topic/angle for this week's content")
    ap.add_argument("--cta-link", default="https://join-kynd.netlify.app")
    ap.add_argument("--remix", help="Optional Dan-Koe-style remix line to open with")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list-topics", action="store_true")
    args = ap.parse_args()

    if args.list_topics:
        if GEN.exists():
            for d in sorted(GEN.iterdir()):
                print("-", d.name)
        else:
            print("(none generated yet)")
        return

    if not args.topic:
        ap.error("--topic is required (or use --list-topics)")

    cuts = build_cuts(args.topic, args.cta_link, args.remix)

    if args.dry_run:
        for k, v in cuts.items():
            print(f"\n===== {k.upper()} =====\n{v}")
        return

    slug = re.sub(r"[^a-z0-9]+", "-", args.topic.lower()).strip("-")[:60]
    out = GEN / slug
    out.mkdir(parents=True, exist_ok=True)
    meta = {
        "topic": args.topic,
        "cta_link": args.cta_link,
        "remix": args.remix,
        "generated": str(date.today()),
        "files": {k: f"{k}.md" for k in cuts},
    }
    for k, v in cuts.items():
        (out / f"{k}.md").write_text(v, encoding="utf-8")
    (out / "_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Generated 4 cuts -> {out}")
    print("Run --list-topics to see all. Nothing posted or deployed.")


if __name__ == "__main__":
    main()
