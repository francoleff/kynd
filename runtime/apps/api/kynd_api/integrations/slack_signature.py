"""Slack request signature verification.

Implements Slack's own documented scheme exactly:
https://docs.slack.dev/authentication/verifying-requests-from-slack/

    basestring = "v0:" + timestamp + ":" + raw_body
    signature  = "v0=" + hex(hmac_sha256(signing_secret, basestring))

No invented cryptography — HMAC-SHA256 via stdlib `hmac`/`hashlib`, exactly
Slack's own reference implementation. The two things that make this an
actual security boundary rather than a decoration:

1. The RAW request body is what gets signed — never a re-serialised/parsed
   version, which would differ in whitespace/key order and always fail.
2. Comparison is constant-time (`hmac.compare_digest`), and the timestamp is
   checked against a replay window BEFORE the signature is computed at all
   (mission requirement: never trust an unverified request).
"""

from __future__ import annotations

import hashlib
import hmac
import time

# Slack's own documented tolerance. A wider window increases the replay
# attack surface for no operational benefit — legitimate requests arrive in
# milliseconds, not minutes.
MAX_TIMESTAMP_SKEW_SECONDS = 60 * 5


class SlackSignatureError(Exception):
    """A Slack request failed verification. Never distinguishes WHY in the
    response — the caller gets a generic 401, matching the rest of the
    codebase's rule against giving an attacker a signal to iterate against."""


def verify_slack_signature(
    *,
    signing_secret: str,
    raw_body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
) -> None:
    """Raise SlackSignatureError unless this request is authentically Slack's.

    Every failure path raises the same exception type with no signal about
    which check failed — missing headers, a stale timestamp, and a bad HMAC
    are indistinguishable to the caller, exactly as they should be.
    """
    if not signing_secret:
        raise SlackSignatureError("Slack signing secret is not configured")
    if not timestamp_header or not signature_header:
        raise SlackSignatureError("Missing Slack signature headers")

    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise SlackSignatureError("Malformed Slack timestamp header") from exc

    # Replay protection: reject anything more than 5 minutes stale BEFORE
    # doing any cryptographic work on it.
    if abs(time.time() - timestamp) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise SlackSignatureError("Slack request timestamp is outside the allowed window")

    basestring = b"v0:" + str(timestamp).encode("ascii") + b":" + raw_body
    computed = "v0=" + hmac.new(
        signing_secret.encode("utf-8"), basestring, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed, signature_header):
        raise SlackSignatureError("Slack signature does not match")
