#!/usr/bin/env python3
"""Read-only pull of Franco's own Discord messages across Kynd channels.

Why this exists: the voice loop re-pulls every wakeup. The Discord REST API 403s
(Cloudflare 1010) unless a browser-like User-Agent is sent. This script encodes
that fix so future wakeups don't re-derive it.

Resilience (hardened after the v23 40333 incident):
- Retries transient HTTP errors (incl. Discord 40333 "internal network error") a
  few times with backoff, so a transient blip doesn't yield a false 0.
- If a channel still fails after retries, it is skipped (not counted as 0), and a
  clear warning is printed so the wakeup never silently reports "0 new".
- Never writes raw.json itself — it only READS the discord_franco_livepull.json
  safety snapshot for sanity-checking counts. The snapshot is maintained
  separately. This script is read-only and never posts.

Output: prints each Franco message (channel, id, content) + FRANCO_MSGS_THIS_PULL.
Read-only. Never posts.
"""
import json, time, urllib.request, urllib.error, os

TOKEN_FILE = '/Users/francoleff/discord_token.txt'
SNAPSHOT = '/Users/francoleff/workspace/kynd/discord_franco_livepull.json'
GUILD = '1531461589432012930'
# Hardcoded fallback list (used only if guild enumeration fails).
CHANNELS_FALLBACK = {
    'general': '1531461592963878914',
    'announcements': '1531473269188722838',
    'wins': '1531473741324877934',
    'ai-questions': '1536730942578626673',
    'work-with-me': '1534638838838857738',
    'community-projects': '1531472199574224998',
    'introduce-yourself': '1531469326727512235',
    'ideas-and-feedback': '1536733469483204678',
    'hermes-questions': '1531474732917194762',
    'start-here': '1537050807722188800',
}
# Channel types we can READ messages from.
SCAN_TYPES = {0, 5, 10, 11, 12}  # text, announcement, (some others)
HEADER = {
    'Authorization': 'Bot ' + open(TOKEN_FILE).read().strip(),
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) DiscordBot/1.0',
}
MAX_RETRIES = 3


def guild_channels():
    """Enumerate ALL guild channels (dynamic — catches new/renamed channels)."""
    url = f'https://discord.com/api/v10/guilds/{GUILD}/channels'
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=HEADER)
            chs = json.load(urllib.request.urlopen(req, timeout=20))
            out = {}
            for c in chs:
                if c.get('type') in SCAN_TYPES and c.get('id'):
                    out[c.get('name') or c['id']] = c['id']
            return out
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(attempt * 1.5)
    return {}


def pull_channel(cid):
    """Return list of messages, or raise after retries."""
    url = f'https://discord.com/api/v10/channels/{cid}/messages?limit=100'
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers=HEADER)
            return json.load(urllib.request.urlopen(req, timeout=20))
        except urllib.error.HTTPError as e:
            last = e
            # 40333 / 5xx = transient; 4xx (except 429) = likely persistent
            if e.code == 429:
                time.sleep(2)
            elif 500 <= e.code < 600 or e.code == 40333:
                time.sleep(attempt * 1.5)
            else:
                raise
        except Exception as e:  # network blip
            last = e
            time.sleep(attempt * 1.5)
    raise last or RuntimeError('pull failed')


def main():
    found = []
    failed = []
    # Try dynamic enumeration first; fall back to hardcoded list if it fails.
    try:
        channels = guild_channels()
        src = 'enumerated'
    except Exception:
        channels = dict(CHANNELS_FALLBACK)
        src = 'fallback'
    if not channels:
        channels = dict(CHANNELS_FALLBACK)
        src = 'fallback'
    print(f'CHANNEL SOURCE: {src} ({len(channels)} channels)')
    for name, cid in channels.items():
        try:
            msgs = pull_channel(cid)
        except Exception as e:
            failed.append((name, str(e)))
            continue
        for m in msgs:
            a = m.get('author', {})
            if a.get('username') == 'francoleff' and m.get('content', '').strip():
                found.append((name, m['id'], m['content'].strip()))
    print(f'FRANCO_MSGS_THIS_PULL: {len(found)}')
    for name, mid, content in found:
        print(f'\n=== [{name}] {mid}\n{content}')
    if failed:
        print(f'\nWARNING: {len(failed)} channel(s) failed to pull (transient?):')
        for name, err in failed:
            print(f'  {name}: {err}')
        # sanity-check against the safety snapshot so a failed pull is never
        # mistaken for "0 new"
        try:
            snap = json.load(open(SNAPSHOT))
            print(f'SAFETY SNAPSHOT has {len(snap)} msgs — if this pull shows 0, '
                  f'trust the snapshot, not this run.')
        except Exception:
            pass


if __name__ == '__main__':
    main()
