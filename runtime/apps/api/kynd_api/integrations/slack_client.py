"""Outbound Slack API calls. The one place that speaks to Slack's HTTP API.

Kept deliberately thin: this module has NO knowledge of workspaces, tenancy,
governance, or credentials-at-rest — it takes an already-decrypted bot token
and makes one HTTP call. Decryption happens in slack_service.py, immediately
before this is invoked, and the token is never logged or returned.

This is the extension point future phases (AI proposals, real capability
execution) will call through — but ONLY via a runtime tool handler closure
built in registry_factory.py's `handler_factory`, exactly like every other
integration (see docs/saas/SAAS_ARCHITECTURE_AUDIT.md W-4: the model/proposal
layer never touches a credential directly). Phase 9 stops before that wiring
exists; this module is standalone and unused by the execution path yet.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

SLACK_API_BASE = "https://slack.com/api"
DEFAULT_TIMEOUT_SECONDS = 10.0


class SlackApiError(Exception):
    """A Slack API call failed. Never fabricated — always backed by a real
    HTTP response (or a real network failure)."""


@dataclass(frozen=True)
class SlackApiResult:
    ok: bool
    data: dict
    error: str | None = None


def _post(token: str, method: str, payload: dict) -> SlackApiResult:
    """One authenticated call to a Slack Web API method.

    Slack's own convention: HTTP 200 with `{"ok": false, "error": "..."}` is
    how Slack reports a FAILED call, not an HTTP error status. Both a network
    failure and a Slack-reported failure surface as SlackApiResult(ok=False)
    — never silently treated as success.
    """
    try:
        response = httpx.post(
            f"{SLACK_API_BASE}/{method}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise SlackApiError(f"Could not reach Slack: {exc}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise SlackApiError("Slack returned a non-JSON response") from exc

    ok = bool(body.get("ok"))
    return SlackApiResult(ok=ok, data=body, error=None if ok else body.get("error"))


def test_auth(token: str) -> SlackApiResult:
    """`auth.test` — the standard Slack "is this token valid" call.

    Used by the /integrations/slack/test endpoint. Real network call; the
    caller decides what CONNECTED/ERROR transition the result justifies.
    """
    return _post(token, "auth.test", {})


def post_message(token: str, *, channel: str, text: str) -> SlackApiResult:
    """`chat.postMessage` — the basic outbound message primitive.

    No governance, no approval check, no audit write — this is the raw
    transport. A future capability handler (registered per Phase 4's
    connector-rule pattern) is what will call this from inside a runtime
    Action; nothing calls it from Phase 9's own code paths yet except the
    manual /integrations/slack/test endpoint's optional message parameter.
    """
    return _post(token, "chat.postMessage", {"channel": channel, "text": text})
