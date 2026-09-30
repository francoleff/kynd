"""Inbound Slack events — the ONLY unauthenticated endpoint Slack talks to.

There is no session cookie here; Slack cannot send one. Trust instead comes
entirely from HMAC signature verification (slack_signature.py), checked
BEFORE the raw body is parsed as JSON and BEFORE any database lookup.

Tenant resolution: the verified payload's `team_id` is looked up against
`Integration.external_id` (slack_service.resolve_workspace_by_slack_team_id)
— set at CONNECT time by an authenticated Kynd user, never accepted as an
authority from this endpoint. An unrecognised team_id (a team_id that was
never connected here) resolves to no workspace and the event is acknowledged
but discarded — never guessed at, never attributed to the wrong tenant.

Phase 9 scope: verify, resolve tenant, record a verified inbound event.
Nothing here creates a proposal or reaches the runtime — see
kynd_api/integrations/slack_client.py's module docstring for the future
extension point.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import SessionLocal
from ..integrations.slack_signature import SlackSignatureError, verify_slack_signature
from ..models import AuditEventType, AuditOutcome
from ..services import audit_service, slack_service

router = APIRouter(prefix="/webhooks/slack", tags=["webhooks"])


@router.post("/events", status_code=status.HTTP_200_OK)
async def receive_slack_event(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
) -> dict:
    settings = get_settings()
    raw_body = await request.body()

    try:
        verify_slack_signature(
            signing_secret=settings.slack_signing_secret or "",
            raw_body=raw_body,
            timestamp_header=x_slack_request_timestamp,
            signature_header=x_slack_signature,
        )
    except SlackSignatureError as exc:
        # No signal about which check failed — a generic 401 for every
        # verification failure, same class of exception either way.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed event payload"
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed event payload")

    # Slack's one-time URL verification handshake when the events URL is
    # first configured. Not a real event — answered immediately, no DB work.
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed url_verification payload"
            )
        return {"challenge": challenge}

    team_id = payload.get("team_id")
    event_type = payload.get("event", {}).get("type") if isinstance(payload.get("event"), dict) else None

    if not isinstance(team_id, str) or not team_id:
        # A verified-but-teamless payload: acknowledge Slack (a 4xx/5xx here
        # causes Slack to retry indefinitely) but record nothing, since there
        # is no resource_type/resource_id worth recording it against and
        # nothing app-level actually happened.
        return {"status": "ignored"}

    db: DbSession = SessionLocal()
    try:
        workspace = slack_service.resolve_workspace_by_slack_team_id(db, team_id)
        if workspace is None:
            # A signature-valid event from a team Kynd has no connected
            # integration for. Acknowledge without attributing it to any
            # tenant — there is no workspace to record it against, and
            # guessing one would be exactly the "trust a Slack-supplied
            # tenant identifier" mistake the mission forbids.
            return {"status": "ignored"}

        audit_service.record(
            db,
            workspace,
            event_type=AuditEventType.SLACK_EVENT_RECEIVED,
            outcome=AuditOutcome.SUCCESS,
            resource_type="slack_event",
            resource_id=None,
            actor_user_id=None,  # Slack-originated, not a Kynd user action
            metadata={"slack_event_type": event_type, "team_id": team_id},
        )
        db.commit()
    finally:
        db.close()

    return {"status": "received"}
