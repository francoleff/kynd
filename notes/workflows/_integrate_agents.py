#!/usr/bin/env python3
"""
Integration harness for KYND CEO pass.

When the 6 strategy/research agents finish, their markdown summaries re-enter the
conversation. This script takes their raw output (passed as a directory of .md files)
and:
  1. Writes each agent's output to the correct KYND/ subfolder.
  2. Extracts the tool tables from the tools-researcher output and upserts them
     into KYND_Library.xlsx (Top 50 + Emerging 20 sheets), preserving the README/
     Category Index sheets.
  3. Regenerates the Category Index sheet from the final tool list.

Run (after agent outputs are saved to ./agent_outputs/):
  python3 _integrate_agents.py

NOTE: This is a fallback harness. In the live session, the parent agent integrates
text outputs directly into KYND/ docs and refreshes the xlsx via execute_code, so this
script is the repeatable system for FUTURE runs.
"""
import os, glob
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
AGENT_OUT = os.path.join(HERE, "agent_outputs")
XLSX = os.path.join(ROOT, "KYND_Library.xlsx")

ROUTING = {
    "kynd-strategy": ("strategy", "kynd_strategy.md"),
    "business": ("business", "business.md"),
    "content": ("content", "content.md"),
    "products": ("products", "products.md"),
    "strategy": ("strategy", "ceo_strategy.md"),
    "tools": ("library", "tools_research.md"),
}

def route_outputs():
    if not os.path.isdir(AGENT_OUT):
        print("No agent_outputs/ dir; nothing to route.")
        return
    files = glob.glob(os.path.join(AGENT_OUT, "*.md"))
    for fp in files:
        name = os.path.basename(fp).lower()
        for key, (folder, fname) in ROUTING.items():
            if key in name:
                dst = os.path.join(ROOT, folder, fname)
                with open(fp) as f:
                    data = f.read()
                with open(dst, "w") as f:
                    f.write(data)
                print(f"Routed {fp} -> {dst}")
                break

def parse_tool_table(md_text):
    rows = []
    for line in md_text.splitlines():
        if line.startswith("|") and "Name" not in line and "---" not in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 6:
                rows.append(cells[:6])
    return rows

def update_xlsx(top_rows, emerging_rows):
    if not os.path.isfile(XLSX):
        print("xlsx not found; skipping.")
        return
    wb = openpyxl.load_workbook(XLSX)
    cols = ["Tool","Category","Description","Use Case for Builder","Pricing","URL","Kynd Value (to fill)"]
    if "Top 50 Tools" in wb.sheetnames:
        ws = wb["Top 50 Tools"]
        # keep header, replace data rows
        for r in range(ws.max_row, 1, -1):
            ws.delete_rows(r)
        for row in top_rows[:50]:
            ws.append(list(row) + [""])
    if "Emerging 20" in wb.sheetnames:
        ws = wb["Emerging 20"]
        for r in range(ws.max_row, 1, -1):
            ws.delete_rows(r)
        for row in emerging_rows[:20]:
            ws.append(list(row) + [""])
    # rebuild category index
    from collections import Counter
    cat = Counter(r[1] for r in top_rows[:50])
    if "Category Index" in wb.sheetnames:
        ws = wb["Category Index"]
        for r in range(ws.max_row, 1, -1):
            ws.delete_rows(r)
        for k, v in sorted(cat.items(), key=lambda x: -x[1]):
            ws.append([k, v])
    wb.save(XLSX)
    print(f"Updated {XLSX}: {len(top_rows[:50])} top, {len(emerging_rows[:20])} emerging.")

def main():
    route_outputs()
    tools_md = os.path.join(AGENT_OUT, "tools.md")
    if os.path.isfile(tools_md):
        text = open(tools_md).read()
        parts = text.split("## EMERGING")
        top = parse_tool_table(parts[0])
        emer = parse_tool_table(parts[1]) if len(parts) > 1 else []
        update_xlsx(top, emer)
    print("Integration complete.")

if __name__ == "__main__":
    main()
