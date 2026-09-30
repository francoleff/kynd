"""Phase 9 — Slack scaffold.

Mocks ALL external Slack HTTP calls (httpx.post is monkeypatched) — no real
Slack workspace is ever contacted, and no test fabricates a "delivered"
result the mock did not actually produce.

Covers: connect/disconnect/test (authenticated, tenant-scoped), inbound
webhook signature verification (valid/invalid/malformed/replay), tenant
resolution from a verified event, and audit integration.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from kynd_api.config import reset_settings_cache
from kynd_api.security import crypto


SIGNING_SECRET = "test-signing-secret"


@pytest.fixture(autouse=True)
def _configured_key(monkeypatch):
    monkeypatch.setenv(crypto.KEY_ENV_VAR, crypto.generate_key())


@pytest.fixture(autouse=True)
def _configured_slack_signing_secret(monkeypatch):
    monkeypatch.setenv("KYND_SLACK_SIGNING_SECRET", SIGNING_SECRET)
    reset_settings_cache()
    yield
    reset_settings_cache()


def _sign(body: bytes, timestamp: str, secret: str = SIGNING_SECRET) -> str:
    basestring = b"v0:" + timestamp.encode("ascii") + b":" + body
    return "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def _slack_headers(body: bytes, *, timestamp: str | None = None, secret: str = SIGNING_SECRET) -> dict:
    ts = timestamp or str(int(time.time()))
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": _sign(body, ts, secret),
    }


# ---------------------------------------------------------------------------
# Authenticated integration management
# ---------------------------------------------------------------------------


def test_connect_slack_stores_encrypted_and_returns_masked_hint(client, owner):
    resp = client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-fake-token-abc123", "team_id": "T12345", "display_name": "My Slack"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "CONNECTED"
    assert body["team_id"] == "T12345"
    assert "bot_token" not in body
    assert "xoxb-fake-token-abc123" not in json.dumps(body)
    assert body["credential_hint"].endswith("3123") or body["credential_hint"].startswith("xoxb")


def test_get_slack_integration_status(client, owner):
    assert client.get("/integrations/slack").json() is None

    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
    )
    resp = client.get("/integrations/slack")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONNECTED"


def test_connect_twice_is_rejected(client, owner):
    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
    )
    resp = client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-def", "team_id": "T2", "display_name": "Slack Again"},
    )
    assert resp.status_code == 409


def test_disconnect_wipes_credential(client, owner, db):
    from kynd_api.models import Integration

    connected = client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
    ).json()

    resp = client.post("/integrations/slack/disconnect")
    assert resp.status_code == 200
    assert resp.json()["status"] == "DISCONNECTED"

    row = db.get(Integration, connected["id"])
    db.refresh(row)
    assert row.credential_ciphertext is None
    assert row.credential_key_id is None


def test_disconnect_when_never_connected_is_404(client, owner):
    resp = client.post("/integrations/slack/disconnect")
    assert resp.status_code == 404


def test_reconnect_after_disconnect_works(client, owner):
    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
    )
    client.post("/integrations/slack/disconnect")

    resp = client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-new", "team_id": "T1", "display_name": "Slack"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "CONNECTED"


def test_test_endpoint_calls_real_mocked_slack_api(client, owner, monkeypatch):
    """`auth.test` never fabricated — result comes from the (mocked) HTTP call."""
    import httpx

    class FakeResponse:
        def json(self):
            return {"ok": True, "team_id": "T1", "user_id": "U1"}

    calls = []

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, json, headers))
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)

    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-realtoken", "team_id": "T1", "display_name": "Slack"},
    )
    resp = client.post("/integrations/slack/test")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "error": None}
    assert len(calls) == 1
    assert calls[0][0].endswith("/auth.test")
    assert calls[0][2]["Authorization"] == "Bearer xoxb-realtoken"


def test_test_endpoint_reports_real_slack_failure(client, owner, monkeypatch):
    import httpx

    class FakeResponse:
        def json(self):
            return {"ok": False, "error": "invalid_auth"}

    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse())

    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-bad", "team_id": "T1", "display_name": "Slack"},
    )
    resp = client.post("/integrations/slack/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "invalid_auth"


def test_test_endpoint_when_not_connected_is_404(client, owner):
    resp = client.post("/integrations/slack/test")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Permissions and tenant isolation
# ---------------------------------------------------------------------------


def test_viewer_cannot_connect(client, owner, db):
    from sqlalchemy import select

    from kynd_api.models import Membership, Role, User

    signup = client.post(
        "/auth/signup",
        json={
            "email": "slack-viewer@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Slack Viewer WS",
        },
    )
    assert signup.status_code == 201

    viewer_user = db.execute(
        select(User).where(User.email == "slack-viewer@example.com")
    ).scalar_one()
    db.add(Membership(user_id=viewer_user.id, workspace_id=owner["workspace"]["id"], role=Role.VIEWER))
    db.commit()

    client.post(
        "/auth/login",
        json={"email": "slack-viewer@example.com", "password": "correct-horse-battery-staple"},
    )
    resp = client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
        headers={"X-Kynd-Workspace": owner["workspace"]["id"]},
    )
    assert resp.status_code == 403


def test_cross_workspace_isolation(client, owner):
    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T1", "display_name": "Slack"},
    )

    other = client.post(
        "/auth/signup",
        json={
            "email": "slack-other@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Slack Other Co",
        },
    )
    assert other.status_code == 201

    resp = client.get("/integrations/slack")
    assert resp.status_code == 200
    assert resp.json() is None


def test_unauthenticated_request_is_401(client):
    resp = client.get("/integrations/slack")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Inbound webhook: signature verification
# ---------------------------------------------------------------------------


def test_webhook_url_verification_handshake(client):
    body = json.dumps({"type": "url_verification", "challenge": "abc123"}).encode()
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "abc123"}


def test_webhook_valid_signature_and_known_team_records_event(client, owner):
    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T999", "display_name": "Slack"},
    )

    body = json.dumps(
        {"type": "event_callback", "team_id": "T999", "event": {"type": "message"}}
    ).encode()
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}

    events = client.get("/audit", params={"event_type": "slack.event_received"}).json()
    assert len(events) == 1
    assert events[0]["resource_type"] == "slack_event"
    assert events[0]["actor_user_id"] is None
    assert events[0]["metadata"]["team_id"] == "T999"


def test_webhook_invalid_signature_is_401(client):
    body = json.dumps({"type": "event_callback", "team_id": "T1"}).encode()
    ts = str(int(time.time()))
    resp = client.post(
        "/webhooks/slack/events",
        content=body,
        headers={"X-Slack-Request-Timestamp": ts, "X-Slack-Signature": "v0=deadbeef"},
    )
    assert resp.status_code == 401


def test_webhook_missing_headers_is_401(client):
    body = json.dumps({"type": "event_callback", "team_id": "T1"}).encode()
    resp = client.post("/webhooks/slack/events", content=body)
    assert resp.status_code == 401


def test_webhook_wrong_signing_secret_is_401(client):
    body = json.dumps({"type": "event_callback", "team_id": "T1"}).encode()
    resp = client.post(
        "/webhooks/slack/events",
        content=body,
        headers=_slack_headers(body, secret="wrong-secret"),
    )
    assert resp.status_code == 401


def test_webhook_stale_timestamp_is_401(client):
    body = json.dumps({"type": "event_callback", "team_id": "T1"}).encode()
    stale_ts = str(int(time.time()) - 60 * 10)  # 10 minutes old
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body, timestamp=stale_ts)
    )
    assert resp.status_code == 401


def test_webhook_malformed_json_is_400(client):
    body = b"not json at all {{{"
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 400


def test_webhook_unrecognised_team_id_is_ignored_not_attributed(client, owner):
    """A verified event from a team Kynd never connected must not be
    guessed into any tenant's audit trail."""
    body = json.dumps(
        {"type": "event_callback", "team_id": "T_UNKNOWN", "event": {"type": "message"}}
    ).encode()
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}

    events = client.get("/audit").json()
    assert events == []


def test_webhook_missing_team_id_is_ignored(client):
    body = json.dumps({"type": "event_callback", "event": {"type": "message"}}).encode()
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ignored"}


def test_webhook_does_not_trust_a_workspace_id_in_the_payload(client, owner):
    """Even if a malicious payload includes a workspace_id field, tenant
    resolution ONLY ever comes from Integration.external_id lookup."""
    other = client.post(
        "/auth/signup",
        json={
            "email": "webhook-other@example.com",
            "password": "correct-horse-battery-staple",
            "workspace_name": "Webhook Other Co",
        },
    )
    other_workspace_id = other.json()["workspace"]["id"]

    client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    client.post(
        "/integrations/slack/connect",
        json={"bot_token": "xoxb-abc", "team_id": "T777", "display_name": "Slack"},
        headers={"X-Kynd-Workspace": owner["workspace"]["id"]},
    )

    body = json.dumps(
        {
            "type": "event_callback",
            "team_id": "T777",
            "workspace_id": other_workspace_id,  # forged, must be ignored
            "event": {"type": "message"},
        }
    ).encode()
    resp = client.post(
        "/webhooks/slack/events", content=body, headers=_slack_headers(body)
    )
    assert resp.status_code == 200

    # The "client" session cookie is now the OTHER user's (last signup wins).
    # Re-authenticate as each to read their own workspace's audit trail.
    client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    owner_events = client.get(
        "/audit", headers={"X-Kynd-Workspace": owner["workspace"]["id"]}
    ).json()

    client.post(
        "/auth/login",
        json={"email": "webhook-other@example.com", "password": "correct-horse-battery-staple"},
    )
    other_events = client.get(
        "/audit", headers={"X-Kynd-Workspace": other_workspace_id}
    ).json()
    assert any(e["event_type"] == "slack.event_received" for e in owner_events)
    assert not any(e["event_type"] == "slack.event_received" for e in other_events)


def test_webhook_no_signing_secret_configured_fails_closed(client, monkeypatch):
    monkeypatch.delenv("KYND_SLACK_SIGNING_SECRET", raising=False)
    reset_settings_cache()
    try:
        body = json.dumps({"type": "event_callback", "team_id": "T1"}).encode()
        resp = client.post(
            "/webhooks/slack/events", content=body, headers=_slack_headers(body)
        )
        assert resp.status_code == 401
    finally:
        reset_settings_cache()
