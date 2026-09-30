"""Audit Center routes — read-only over the SaaS control plane's own
activity trail (kynd_api.models.AuditEvent).

Distinct from `/executions` (Phase 7), which reads the runtime's own
execution_log. This endpoint answers "what happened in the product" —
governance changes, approval decisions, team/workspace changes — not "what
did the runtime execute". See audit_service.py module docstring.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import AuditEventType, AuditOutcome
from ..schemas import AuditEventOut
from ..security.permissions import Permission
from ..services import audit_service
from sqlalchemy.orm import Session as DbSession

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    event_type: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    actor_user_id: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    ctx: WorkspaceContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: DbSession = Depends(get_db),
) -> list[AuditEventOut]:
    parsed_event_type: AuditEventType | None = None
    if event_type is not None:
        try:
            parsed_event_type = AuditEventType(event_type)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown event_type: {event_type!r}",
            ) from exc

    parsed_outcome: AuditOutcome | None = None
    if outcome is not None:
        try:
            parsed_outcome = AuditOutcome(outcome.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown outcome: {outcome!r}",
            ) from exc

    rows = audit_service.list_events(
        db,
        ctx.workspace,
        event_type=parsed_event_type,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=actor_user_id,
        outcome=parsed_outcome,
        since=since,
        until=until,
        limit=limit,
    )
    return [AuditEventOut.from_model(row) for row in rows]


@router.get("/{event_id}", response_model=AuditEventOut)
def get_audit_event(
    event_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.AUDIT_READ)),
    db: DbSession = Depends(get_db),
) -> AuditEventOut:
    event = audit_service.get_event(db, ctx.workspace, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit event not found")
    return AuditEventOut.from_model(event)
