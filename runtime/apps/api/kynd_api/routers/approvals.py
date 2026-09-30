"""Approval Center routes.

Every handler resolves its workspace from `require_permission(...)`, exactly
like `workspace.py`. `ACTION_PROPOSE` files a request; `APPROVAL_DECIDE`
approves or rejects one; `ACTION_EXECUTE` runs an already-approved one
through the canonical execute_action path — the permission matrix
(kynd_api/security/permissions.py) already keeps a VIEWER from doing any of
the three, and keeps an OPERATOR who can approve/execute from being able to
edit the governance rules that decide what's allowed in the first place.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import ApprovalRequestStatus, AuditEventType, AuditOutcome
from ..runtime.handlers import production_handler_factory
from ..schemas import (
    ApprovalDecisionRequest,
    ApprovalRequestCreate,
    ApprovalRequestOut,
    ExecuteApprovalRequest,
    ExecutionOutcomeOut,
)
from ..security.permissions import Permission
from ..services import approval_service, audit_service
from ..services.execution_service import ExecutionOutcome

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.post("", response_model=ApprovalRequestOut, status_code=status.HTTP_201_CREATED)
def create_approval_request(
    payload: ApprovalRequestCreate,
    ctx: WorkspaceContext = Depends(require_permission(Permission.ACTION_PROPOSE)),
    db: DbSession = Depends(get_db),
) -> ApprovalRequestOut:
    try:
        request = approval_service.create_request(
            db,
            ctx.workspace,
            capability=payload.capability,
            action_type=payload.action_type,
            target=payload.target,
            amount=payload.amount,
            params=payload.params,
            reason=payload.reason,
            requested_by_user_id=ctx.user.id,
        )
    except approval_service.ApprovalServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    db.commit()
    db.refresh(request)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.APPROVAL_REQUESTED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="approval_request",
        resource_id=request.id,
        actor_user_id=ctx.user.id,
        metadata={"capability": request.capability, "action_type": request.action_type},
        approval_request_id=request.id,
    )
    db.commit()

    return ApprovalRequestOut.from_model(request)


@router.get("", response_model=list[ApprovalRequestOut])
def list_approval_requests(
    request_status: str | None = None,
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_READ)),
    db: DbSession = Depends(get_db),
) -> list[ApprovalRequestOut]:
    status_filter: ApprovalRequestStatus | None = None
    if request_status:
        try:
            status_filter = ApprovalRequestStatus(request_status.upper())
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown status: {request_status!r}",
            ) from exc

    rows = approval_service.list_requests(db, ctx.workspace, status_filter=status_filter)
    db.commit()  # persists any lazy PENDING -> EXPIRED transitions
    return [ApprovalRequestOut.from_model(row) for row in rows]


@router.get("/{request_id}", response_model=ApprovalRequestOut)
def get_approval_request(
    request_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_READ)),
    db: DbSession = Depends(get_db),
) -> ApprovalRequestOut:
    try:
        request = approval_service.get_request(db, ctx.workspace, request_id)
    except approval_service.ApprovalNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    db.commit()
    return ApprovalRequestOut.from_model(request)


def _decision_error(exc: approval_service.ApprovalServiceError) -> HTTPException:
    if isinstance(exc, approval_service.ApprovalNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (approval_service.ApprovalExpired, approval_service.ApprovalNotPending)):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{request_id}/approve", response_model=ApprovalRequestOut)
def approve_approval_request(
    request_id: str,
    payload: ApprovalDecisionRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_DECIDE)),
    db: DbSession = Depends(get_db),
) -> ApprovalRequestOut:
    try:
        result = approval_service.approve_request(
            db,
            ctx.workspace,
            request_id,
            decided_by_user_id=ctx.user.id,
            note=payload.note,
        )
    except approval_service.ApprovalServiceError as exc:
        db.rollback()
        raise _decision_error(exc) from exc

    db.commit()
    db.refresh(result.request)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.APPROVAL_APPROVED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="approval_request",
        resource_id=result.request.id,
        actor_user_id=ctx.user.id,
        metadata={"capability": result.request.capability, "note": payload.note},
        approval_request_id=result.request.id,
        runtime_execution_id=None,
    )
    db.commit()

    return ApprovalRequestOut.from_model(result.request)


def _execution_error(exc: approval_service.ApprovalServiceError) -> HTTPException:
    if isinstance(exc, approval_service.ApprovalNotFound):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            approval_service.ApprovalExpired,
            approval_service.ApprovalNotApproved,
            approval_service.ApprovalHasNoRuntimeToken,
        ),
    ):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/{request_id}/execute", response_model=ExecutionOutcomeOut)
def execute_approval_request(
    request_id: str,
    payload: ExecuteApprovalRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.ACTION_EXECUTE)),
    db: DbSession = Depends(get_db),
) -> ExecutionOutcomeOut:
    """Run an already-approved request through the runtime, for real.

    This is the ONLY route that redeems a runtime approval token — it calls
    `approval_service.execute_approved_request`, which calls
    `execution_service.execute_action`, the SaaS's single canonical entry
    point into the runtime (test_runtime_adapter.py's
    TestSingleExecutionPath proves no second path exists). Nothing here
    constructs an Executor, checks a rule, or decides allow/deny — the
    runtime does, exactly as it did before this endpoint existed.
    """
    try:
        result = approval_service.execute_approved_request(
            db,
            ctx.workspace,
            request_id,
            handler_factory=production_handler_factory,
            idempotency_key=payload.idempotency_key,
        )
    except approval_service.ApprovalServiceError as exc:
        db.rollback()
        raise _execution_error(exc) from exc

    db.commit()

    audit_service.record(
        db,
        ctx.workspace,
        event_type={
            ExecutionOutcome.EXECUTED: AuditEventType.ACTION_EXECUTED,
            ExecutionOutcome.FAILED: AuditEventType.ACTION_FAILED,
        }.get(result.outcome, AuditEventType.ACTION_BLOCKED),
        outcome=(
            AuditOutcome.SUCCESS
            if result.outcome == ExecutionOutcome.EXECUTED
            else (AuditOutcome.ERROR if result.outcome == ExecutionOutcome.FAILED else AuditOutcome.DENIED)
        ),
        resource_type="approval_request",
        resource_id=request_id,
        actor_user_id=ctx.user.id,
        metadata={
            "capability": result.capability,
            "action_type": result.action_type,
            "outcome": result.outcome,
        },
        approval_request_id=request_id,
    )
    db.commit()

    return ExecutionOutcomeOut(
        outcome=result.outcome, reason=result.reason, result=result.result
    )


@router.post("/{request_id}/reject", response_model=ApprovalRequestOut)
def reject_approval_request(
    request_id: str,
    payload: ApprovalDecisionRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_DECIDE)),
    db: DbSession = Depends(get_db),
) -> ApprovalRequestOut:
    try:
        request = approval_service.reject_request(
            db,
            ctx.workspace,
            request_id,
            decided_by_user_id=ctx.user.id,
            note=payload.note,
        )
    except approval_service.ApprovalServiceError as exc:
        db.rollback()
        raise _decision_error(exc) from exc

    db.commit()
    db.refresh(request)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.APPROVAL_REJECTED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="approval_request",
        resource_id=request.id,
        actor_user_id=ctx.user.id,
        metadata={"capability": request.capability, "note": payload.note},
        approval_request_id=request.id,
    )
    db.commit()

    return ApprovalRequestOut.from_model(request)
