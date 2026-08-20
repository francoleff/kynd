#!/usr/bin/env python3
"""
Scheduled content-engine runner.

Reads REMIX-LIBRARY.md (a markdown table of Dan Koe original -> Franco remix
pairs), tracks the last-used row in content-state.json, and runs engine.py on
the NEXT row so each scheduled run produces a fresh set of cuts without manual
topic selection.

Safe to run by hand or via launchd. Does NOT post/deploy anything — cuts land
in content-engine/generated/ as drafts for Franco to review.

Intended launchd cadence: weekly (matches the content T-001 cadence).

NOT installed automatically — drop the companion plist into
~/Library/LaunchAgents and load it to activate.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(os.path.dirname(HERE), 'REMIX-LIBRARY.md')
STATE = os.path.join(HERE, 'content-state.json')
ENGINE = os.path.join(HERE, 'engine.py')


def parse_rows(path):
    """Return list of (dan_original, franco_remix) tuples from the markdown table."""
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            if not line.strip().startswith('|'):
                continue
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            # Skip header + separator rows
            if len(cells) < 2:
                continue
            if cells[0].lower().startswith('dan koe') or set(cells[0]) <= set('-: '):
                continue
            dan, franco = cells[0], cells[1]
            if not dan or not franco:
                continue
            rows.append((dan, franco))
    return rows


def next_row(rows):
    last = 0
    if os.path.exists(STATE):
        try:
            last = json.load(open(STATE)).get('last_index', 0)
        except Exception:
            last = 0
    idx = (last + 1) % len(rows)
    return idx, rows[idx]


def main():
    rows = parse_rows(LIBRARY)
    if not rows:
        print('No remix rows found in', LIBRARY)
        return 1
    idx, (dan, franco) = next_row(rows)
    # Franco remix = the topic; Dan original = the remix angle
    cmd = [sys.executable, ENGINE, '--topic', franco, '--remix', dan]
    print(f'Row {idx+1}/{len(rows)}: running engine on remix')
    rc = subprocess.call(cmd)
    if rc == 0:
        json.dump({'last_index': idx}, open(STATE, 'w'))
        print(f'Advanced content-state to row {idx+1}')
    else:
        print('engine.py failed (rc=%d) — state NOT advanced' % rc)
    return rc


if __name__ == '__main__':
    sys.exit(main())
