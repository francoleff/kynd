"""Slack integration management — authenticated, tenant-scoped.

Distinct from `slack_webhooks.py`, which handles UNAUTHENTICATED inbound
Slack traffic verified by HMAC signature instead of a session. This router
is the normal authenticated API surface: a logged-in Kynd user with
INTEGRATION_* permission connects/disconnects/tests their own workspace's
Slack integration, exactly like every other tenant-scoped resource in this
codebase (require_permission + WorkspaceContext).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import AuditEventType, AuditOutcome
from ..schemas import SlackConnectRequest, SlackIntegrationOut, SlackTestResult
from ..security.permissions import Permission
from ..services import audit_service, slack_service

router = APIRouter(prefix="/integrations/slack", tags=["integrations"])


@router.get("", response_model=SlackIntegrationOut | None)
def get_slack_integration(
    ctx: WorkspaceContext = Depends(require_permission(Permission.INTEGRATION_READ)),
    db: DbSession = Depends(get_db),
) -> SlackIntegrationOut | None:
    integration = slack_service.get_integration(db, ctx.workspace)
    if integration is None:
        return None
    return SlackIntegrationOut.from_model(integration)


@router.post("/connect", response_model=SlackIntegrationOut, status_code=status.HTTP_201_CREATED)
def connect_slack(
    payload: SlackConnectRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.INTEGRATION_CONNECT)),
    db: DbSession = Depends(get_db),
) -> SlackIntegrationOut:
    try:
        integration = slack_service.connect(
            db,
            ctx.workspace,
            bot_token=payload.bot_token,
            team_id=payload.team_id,
            display_name=payload.display_name,
            connected_by_user_id=ctx.user.id,
        )
    except slack_service.SlackAlreadyConnected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    db.refresh(integration)

    # The audit event never carries the token or even its hint's origin
    # metadata beyond what's already customer-visible on the integration
    # itself — team_id and display_name are not secrets.
    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.INTEGRATION_CONNECTED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="integration",
        resource_id=integration.id,
        actor_user_id=ctx.user.id,
        metadata={"provider": "SLACK", "team_id": payload.team_id, "display_name": payload.display_name},
    )
    db.commit()

    return SlackIntegrationOut.from_model(integration)


@router.post("/disconnect", response_model=SlackIntegrationOut)
def disconnect_slack(
    ctx: WorkspaceContext = Depends(require_permission(Permission.INTEGRATION_DISCONNECT)),
    db: DbSession = Depends(get_db),
) -> SlackIntegrationOut:
    try:
        integration = slack_service.disconnect(db, ctx.workspace)
    except slack_service.SlackNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    db.refresh(integration)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.INTEGRATION_DISCONNECTED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="integration",
        resource_id=integration.id,
        actor_user_id=ctx.user.id,
        metadata={"provider": "SLACK"},
    )
    db.commit()

    return SlackIntegrationOut.from_model(integration)


@router.post("/test", response_model=SlackTestResult)
def test_slack(
    ctx: WorkspaceContext = Depends(require_permission(Permission.INTEGRATION_TEST)),
    db: DbSession = Depends(get_db),
) -> SlackTestResult:
    """A real `auth.test` call. Never fabricates success — see
    slack_service.test_connection / slack_client.test_auth."""
    try:
        result = slack_service.test_connection(db, ctx.workspace)
    except slack_service.SlackNotConnected as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()

    integration = slack_service.get_integration(db, ctx.workspace)
    audit_service.record(
        db,
        ctx.workspace,
        event_type=(
            AuditEventType.INTEGRATION_TEST_SUCCEEDED
            if result.ok
            else AuditEventType.INTEGRATION_TEST_FAILED
        ),
        outcome=AuditOutcome.SUCCESS if result.ok else AuditOutcome.ERROR,
        resource_type="integration",
        resource_id=integration.id if integration else None,
        actor_user_id=ctx.user.id,
        metadata={"provider": "SLACK", "error": result.error} if not result.ok else {"provider": "SLACK"},
    )
    db.commit()

    return SlackTestResult(ok=result.ok, error=result.error)
