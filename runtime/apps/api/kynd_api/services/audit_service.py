"""The Audit Center's write and read path.

Orchestration only, and specifically NOT a second execution engine: `record`
is called from inside the same transaction as the real change it describes
(governance router, approval router, workspace router), never speculatively
and never retried as background logging. If the surrounding commit rolls
back, the audit row rolls back with it — an audit event that describes a
change which never actually happened would be worse than no event at all.

This module owns the Postgres `AuditEvent` table only. It does not read or
write the runtime's own audit_log/execution_log (per-workspace SQLite) — see
docs/saas/SAAS_ARCHITECTURE_AUDIT.md section 3.2. Where an event corresponds
to a runtime record, only a reference id is stored (see AuditEvent docstring
in models/__init__.py).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import AuditEvent, AuditEventType, AuditOutcome, Workspace


def record(
    db: DbSession,
    workspace: Workspace,
    *,
    event_type: AuditEventType,
    outcome: AuditOutcome,
    resource_type: str,
    resource_id: str | None,
    actor_user_id: str | None,
    metadata: dict[str, Any] | None = None,
    runtime_execution_id: int | None = None,
    approval_request_id: str | None = None,
) -> AuditEvent:
    """Write one audit event. Caller commits — this only flushes.

    Composing inside the caller's own transaction (rather than committing
    here) is deliberate: the audit row and the change it describes must
    live or die together, not have a report of a change that got rolled
    back a moment later.
    """
    event = AuditEvent(
        workspace_id=workspace.id,
        event_type=event_type,
        outcome=outcome,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        event_metadata=metadata or {},
        runtime_execution_id=runtime_execution_id,
        approval_request_id=approval_request_id,
    )
    db.add(event)
    db.flush()
    return event


def list_events(
    db: DbSession,
    workspace: Workspace,
    *,
    event_type: AuditEventType | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_user_id: str | None = None,
    outcome: AuditOutcome | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 200,
) -> list[AuditEvent]:
    """The workspace's own audit trail, newest first, filtered as asked.

    Every filter is an AND. `limit` caps the page — this is a read model,
    not an export; a real export would be a separate, explicitly paginated
    endpoint if the product ever needs one.
    """
    query = select(AuditEvent).where(AuditEvent.workspace_id == workspace.id)

    if event_type is not None:
        query = query.where(AuditEvent.event_type == event_type)
    if resource_type is not None:
        query = query.where(AuditEvent.resource_type == resource_type)
    if resource_id is not None:
        query = query.where(AuditEvent.resource_id == resource_id)
    if actor_user_id is not None:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)
    if outcome is not None:
        query = query.where(AuditEvent.outcome == outcome)
    if since is not None:
        query = query.where(AuditEvent.created_at >= since)
    if until is not None:
        query = query.where(AuditEvent.created_at <= until)

    query = query.order_by(AuditEvent.created_at.desc()).limit(limit)

    return list(db.execute(query).scalars().all())


def get_event(db: DbSession, workspace: Workspace, event_id: str) -> AuditEvent | None:
    """One event, scoped to the workspace — the same tenancy pattern as
    every other loader in this codebase (404 on a cross-tenant id, not 403)."""
    return db.execute(
        select(AuditEvent).where(
            AuditEvent.id == event_id,
            AuditEvent.workspace_id == workspace.id,
        )
    ).scalar_one_or_none()
