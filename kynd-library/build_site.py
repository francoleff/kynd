#!/usr/bin/env python3
"""
Build the Kynd Library markdown into a static HTML site.

Local-only. No deploy, no network. Produces ./_site mirroring the source
tree, with .md -> .html and internal links rewritten. Run from the
kynd-library directory, or anywhere (paths are absolute-safe).

Usage:
    python3 build_site.py            # builds into ./_site
    python3 build_site.py --clean    # wipe _site first

Output is ready to publish to Netlify/GitHub Pages (drop _site/ as the
publish dir). Nothing here touches the live site.
"""
import argparse
import re
import shutil
from pathlib import Path

import markdown
from markdown.extensions import tables, fenced_code, toc

SRC = Path(__file__).resolve().parent
OUT = SRC / "_site"

CSS = """
:root{--bg:#0e0f13;--fg:#e8e8ea;--muted:#9aa0aa;--accent:#7c5cff;--card:#16181f;--line:#262a33}
*{box-sizing:border-box}
body{margin:0;font:16px/1.6-system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
header{padding:18px 24px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:center;flex-wrap:wrap}
header .brand{font-weight:700;letter-spacing:.3px}
header nav a{color:var(--muted);margin-right:14px;font-size:14px}
main{max-width:860px;margin:0 auto;padding:32px 24px 80px}
h1{font-size:32px;line-height:1.2;margin-top:0}
h2{border-bottom:1px solid var(--line);padding-bottom:6px;margin-top:40px}
table{border-collapse:collapse;width:100%;margin:18px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left}
th{background:var(--card)}
blockquote{border-left:3px solid var(--accent);margin:18px 0;padding:4px 16px;color:var(--muted)}
code{background:var(--card);padding:2px 6px;border-radius:4px;font-size:13px}
pre{background:var(--card);padding:14px;border-radius:8px;overflow:auto}
pre code{background:none;padding:0}
.foot{color:var(--muted);font-size:13px;margin-top:60px;border-top:1px solid var(--line);padding-top:16px}
""".strip()


def make_html(md_text: str, rel_root: Path, out_path: Path) -> str:
    # Convert .md links -> .html, preserving relative depth.
    def link_rewrite(m):
        pre, target, post = m.group(1), m.group(2), m.group(3)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        if target.endswith(".md"):
            target = target[:-3] + ".html"
        return f"{pre}{target}{post}"

    body_md = re.sub(r"(\[[^\]]*\]\()([^)]+)(\))", link_rewrite, md_text)

    md = markdown.Markdown(
        extensions=[tables.TableExtension(), fenced_code.FencedCodeExtension(), toc.TocExtension()]
    )
    html_body = md.convert(body_md)
    toc_html = md.toc

    # Title = first H1, else filename.
    m = re.search(r"^#\s+(.+)$", md_text, re.MULTILINE)
    title = m.group(1).strip() if m else out_path.stem

    # Relative root path for assets/nav (how deep is this file?).
    depth = len(out_path.relative_to(OUT).parts) - 1
    root_rel = ("../" * depth) if depth > 0 else "./"

    nav = (
        f'<a href="{root_rel}index.html">Library</a>'
        f'<a href="{root_rel}foundation/README.html">Foundation</a>'
        f'<a href="{root_rel}build/README.html">Build</a>'
        f'<a href="{root_rel}business/README.html">Business</a>'
        f'<a href="{root_rel}personal-os/README.html">Personal OS</a>'
        f'<a href="{root_rel}playbooks/README.html">Playbooks</a>'
        f'<a href="{root_rel}resources/README.html">Resources</a>'
        f'<a href="{root_rel}case-studies/README.html">Case Studies</a>'
        f'<a href="{root_rel}frontier/README.html">Frontier</a>'
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Kynd Library</title>
<style>{CSS}</style>
</head>
<body>
<header><span class="brand">KYND LIBRARY</span><nav>{nav}</nav></header>
<main>
{toc_html}
{html_body}
<div class="foot">Built locally from the Kynd Library markdown. Not yet published — deploy on approval.</div>
</main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    if args.clean and OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(exist_ok=True)

    count = 0
    for md in sorted(SRC.rglob("*.md")):
        rel = md.relative_to(SRC)
        if rel.parts[0] == "_site":
            continue
        out_path = OUT / rel.with_suffix(".html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(make_html(md.read_text(), SRC, out_path), encoding="utf-8")
        count += 1

    print(f"Built {count} pages into {OUT}")
    print(f"Index: file://{OUT / 'index.html'}")


if __name__ == "__main__":
    main()
