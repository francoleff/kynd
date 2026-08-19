import sys
from playwright.sync_api import sync_playwright
from pathlib import Path

OUT = Path("/Users/francoleff/workspace/kynd/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

# (label, url) — curated sites that may share Kynd's vision
TARGETS = [
    ("dankoe", "https://www.dankoe.com"),
    ("indiehackers", "https://www.indiehackers.com"),
    ("every", "https://every.to"),
    ("visakanv", "https://www.visakanv.com"),
    ("nadia", "https://nadia.xyz"),
    ("escapethecity", "https://www.escapethecity.com"),
    ("huggingface", "https://huggingface.co"),
    ("aliabdaal", "https://www.aliabdaal.com"),
]

results = {}
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox"])
    ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                              user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    page = ctx.new_page()
    page.set_default_timeout(25000)
    for label, url in TARGETS:
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            # try to dismiss cookie banners quickly
            path = OUT / f"{label}.png"
            page.screenshot(path=str(path), full_page=False)
            title = page.title()
            results[label] = {"url": url, "path": str(path), "title": title, "ok": True}
            print(f"OK   {label:14s} {url:38s} {title[:50]}")
        except Exception as e:
            results[label] = {"url": url, "ok": False, "error": str(e)[:200]}
            print(f"FAIL {label:14s} {url:38s} {str(e)[:80]}")
    browser.close()

import json
(OUT / "manifest.json").write_text(json.dumps(results, indent=2))
print("\nSaved manifest:", OUT / "manifest.json")
