"""Execution Center routes — read-only history over the runtime's own log.

Nothing here invents a status. The runtime's `execution_log` rows already
carry `allowed` (bool) and `status` (a string set by the executor itself:
"executed" | "denied" | "error", see executor.py `_record`). This module maps
that vocabulary onto ExecutionOutcome's customer-facing names and does not
add a state the runtime never recorded.

Never exposes `params` verbatim without the same credential boundary the
executor itself enforces — belt and braces, since `assert_no_credentials`
already stops a credential from ever being written here in the first place.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import WorkspaceContext, require_permission
from ..runtime.store_factory import get_store
from ..schemas import ExecutionRecordOut
from ..security.permissions import Permission

router = APIRouter(prefix="/executions", tags=["executions"])


def _map_outcome(allowed: bool, run_status: str) -> str:
    """Translate the runtime's own (allowed, status) pair into one word.

    The runtime's vocabulary (executor.py STATUS_*): "allowed", "denied", or
    "failed". This function does not invent anything beyond re-labelling
    those three for the UI; "BLOCKED" vs "FAILED" is exactly
    allowed=False-by-governance vs allowed=True-but-the-integration-failed —
    the distinction the mission calls out as mattering to customer trust.
    """
    if run_status == "allowed":
        return "SUCCEEDED"
    if run_status == "denied":
        return "BLOCKED"
    if run_status == "failed":
        return "FAILED"
    return run_status.upper()


@router.get("", response_model=list[ExecutionRecordOut])
def list_executions(
    limit: int = Query(default=200, ge=1, le=2000),
    ctx: WorkspaceContext = Depends(require_permission(Permission.EXECUTION_READ)),
) -> list[ExecutionRecordOut]:
    """The workspace's own execution history, most recent last (as recorded).

    Reads straight from the workspace's per-tenant SQLite store — the same
    physical isolation boundary proven in the Phase 0 audit (probe 2): there
    is no query to get this wrong, because there is no other tenant's data in
    this file at all.
    """
    store = get_store(ctx.workspace_id)
    rows = store.recent_execution(limit=limit)
    return [
        ExecutionRecordOut(
            id=row["id"],
            ts=row["ts"],
            capability=row["capability"],
            action_type=row.get("action_type"),
            outcome=_map_outcome(bool(row["allowed"]), row["status"]),
            reason=row["reason"],
            idempotency_key=row.get("idempotency_key"),
            error=row.get("error"),
        )
        for row in rows
    ]


@router.get("/{execution_id}", response_model=ExecutionRecordOut)
def get_execution(
    execution_id: int,
    ctx: WorkspaceContext = Depends(require_permission(Permission.EXECUTION_READ)),
) -> ExecutionRecordOut:
    store = get_store(ctx.workspace_id)
    rows = store.recent_execution(limit=10_000)
    match = next((row for row in rows if row["id"] == execution_id), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return ExecutionRecordOut(
        id=match["id"],
        ts=match["ts"],
        capability=match["capability"],
        action_type=match.get("action_type"),
        outcome=_map_outcome(bool(match["allowed"]), match["status"]),
        reason=match["reason"],
        idempotency_key=match.get("idempotency_key"),
        error=match.get("error"),
    )
