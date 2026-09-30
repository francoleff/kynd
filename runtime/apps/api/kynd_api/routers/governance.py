"""Constitution / Governance Builder routes.

Exposes CRUD for WorkspaceCapability and GovernanceRule, plus two read-only
endpoints that let a customer preview what their constitution actually does:

  GET  /governance/preview  -> compile_constitution(...).describe()
  POST /governance/simulate  -> GovernanceGate.check() ONLY (never
                                Broker.request(), which consumes quota —
                                see docs/saas/SAAS_ARCHITECTURE_AUDIT.md
                                probe 5).

The simulate endpoint is contractually side-effect free: it builds a
kynd_runtime Action and runs the gate, which verifies but never consumes an
approval and never touches the broker.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession
from kynd_runtime import Action, GovernanceGate

from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import AuditEventType, AuditOutcome, GovernanceRule, WorkspaceCapability
from ..runtime.constitution_compiler import (
    GovernanceConfigError,
    compile_constitution,
)
from ..schemas import (
    GovernancePreview,
    GovernanceRuleBase,
    GovernanceRuleOut,
    GovernanceRuleUpdate,
    MessageResponse,
    SimulateRequest,
    SimulateResponse,
    WorkspaceCapabilityBase,
    WorkspaceCapabilityOut,
    WorkspaceCapabilityUpdate,
)
from ..security.permissions import Permission
from ..services import audit_service

router = APIRouter(prefix="/governance", tags=["governance"])


# ---------------------------------------------------------------------------
# Shared loaders (tenant-scoped, 404 on cross-tenant — same IDOR-proof
# pattern as workspace.py::_load_member).
# ---------------------------------------------------------------------------

def _load_capability(
    db: DbSession, ctx: WorkspaceContext, capability_id: str
) -> WorkspaceCapability:
    cap = db.execute(
        select(WorkspaceCapability).where(
            WorkspaceCapability.id == capability_id,
            WorkspaceCapability.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if cap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Capability not found"
        )
    return cap


def _load_rule(
    db: DbSession, ctx: WorkspaceContext, rule_id: str
) -> GovernanceRule:
    rule = db.execute(
        select(GovernanceRule).where(
            GovernanceRule.id == rule_id,
            GovernanceRule.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        )
    return rule


def _load_capabilities(
    db: DbSession, workspace_id: str
) -> list[WorkspaceCapability]:
    return (
        db.execute(
            select(WorkspaceCapability)
            .where(WorkspaceCapability.workspace_id == workspace_id)
            .order_by(WorkspaceCapability.created_at.asc())
        )
        .scalars()
        .all()
    )


def _load_rules(db: DbSession, workspace_id: str) -> list[GovernanceRule]:
    return (
        db.execute(
            select(GovernanceRule)
            .where(GovernanceRule.workspace_id == workspace_id)
            .order_by(GovernanceRule.created_at.asc())
        )
        .scalars()
        .all()
    )


# ---------------------------------------------------------------------------
# WorkspaceCapability CRUD
# ---------------------------------------------------------------------------


@router.get("/capabilities", response_model=list[WorkspaceCapabilityOut])
def list_capabilities(
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_READ)),
    db: DbSession = Depends(get_db),
) -> list[WorkspaceCapabilityOut]:
    rows = _load_capabilities(db, ctx.workspace_id)
    return [WorkspaceCapabilityOut.from_model(c) for c in rows]


@router.post(
    "/capabilities",
    response_model=WorkspaceCapabilityOut,
    status_code=status.HTTP_201_CREATED,
)
def create_capability(
    payload: WorkspaceCapabilityBase,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> WorkspaceCapabilityOut:
    # Reject duplicates within the same workspace at the API layer so the
    # database's unique constraint is never the thing a customer hits.
    existing = db.execute(
        select(WorkspaceCapability).where(
            WorkspaceCapability.workspace_id == ctx.workspace_id,
            WorkspaceCapability.name == payload.name,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Capability '{payload.name}' already exists in this workspace",
        )

    cap = WorkspaceCapability(
        workspace_id=ctx.workspace_id,
        name=payload.name,
        enabled=payload.enabled,
        max_amount=payload.max_amount,
        max_calls_per_day=payload.max_calls_per_day,
        allowed_targets=payload.allowed_targets,
        requires_approval=payload.requires_approval,
    )
    db.add(cap)
    db.commit()
    db.refresh(cap)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.CAPABILITY_CREATED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="capability",
        resource_id=cap.id,
        actor_user_id=ctx.user.id,
        metadata={"name": cap.name, "enabled": cap.enabled},
    )
    db.commit()

    return WorkspaceCapabilityOut.from_model(cap)


@router.patch("/capabilities/{capability_id}", response_model=WorkspaceCapabilityOut)
def update_capability(
    capability_id: str,
    payload: WorkspaceCapabilityUpdate,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> WorkspaceCapabilityOut:
    cap = _load_capability(db, ctx, capability_id)

    # Validate the FULL resulting constitution compiles before committing.
    # A capability change can break the constitution (e.g. enabling
    # approval for a capability that has no approval rule), so we compile
    # with the proposed new state and reject if it fails.
    proposed = WorkspaceCapability(
        workspace_id=cap.workspace_id,
        name=cap.name,
        enabled=payload.enabled if payload.enabled is not None else cap.enabled,
        max_amount=(
            payload.max_amount
            if payload.max_amount is not None
            else cap.max_amount
        ),
        max_calls_per_day=(
            payload.max_calls_per_day
            if payload.max_calls_per_day is not None
            else cap.max_calls_per_day
        ),
        allowed_targets=(
            payload.allowed_targets
            if payload.allowed_targets is not None
            else cap.allowed_targets
        ),
        requires_approval=(
            payload.requires_approval
            if payload.requires_approval is not None
            else cap.requires_approval
        ),
    )
    others = [
        c
        for c in _load_capabilities(db, ctx.workspace_id)
        if c.id != cap.id
    ]
    rules = _load_rules(db, ctx.workspace_id)
    try:
        compile_constitution(ctx.workspace, others + [proposed], rules)
    except GovernanceConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if payload.enabled is not None:
        cap.enabled = payload.enabled
    if payload.max_amount is not None:
        cap.max_amount = payload.max_amount
    if payload.max_calls_per_day is not None:
        cap.max_calls_per_day = payload.max_calls_per_day
    if payload.allowed_targets is not None:
        cap.allowed_targets = payload.allowed_targets
    if payload.requires_approval is not None:
        cap.requires_approval = payload.requires_approval

    db.commit()
    db.refresh(cap)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.CAPABILITY_UPDATED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="capability",
        resource_id=cap.id,
        actor_user_id=ctx.user.id,
        metadata={
            "name": cap.name,
            "enabled": cap.enabled,
            "max_amount": cap.max_amount,
            "max_calls_per_day": cap.max_calls_per_day,
            "requires_approval": cap.requires_approval,
        },
    )
    db.commit()

    return WorkspaceCapabilityOut.from_model(cap)


@router.delete("/capabilities/{capability_id}", response_model=MessageResponse)
def delete_capability(
    capability_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    cap = _load_capability(db, ctx, capability_id)
    cap_id, cap_name = cap.id, cap.name
    db.delete(cap)
    db.commit()

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.CAPABILITY_DELETED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="capability",
        resource_id=cap_id,
        actor_user_id=ctx.user.id,
        metadata={"name": cap_name},
    )
    db.commit()

    return MessageResponse(message="Capability deleted")


# ---------------------------------------------------------------------------
# GovernanceRule CRUD
# ---------------------------------------------------------------------------


@router.get("/rules", response_model=list[GovernanceRuleOut])
def list_rules(
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_READ)),
    db: DbSession = Depends(get_db),
) -> list[GovernanceRuleOut]:
    rows = _load_rules(db, ctx.workspace_id)
    return [GovernanceRuleOut.from_model(r) for r in rows]


@router.post(
    "/rules",
    response_model=GovernanceRuleOut,
    status_code=status.HTTP_201_CREATED,
)
def create_rule(
    payload: GovernanceRuleBase,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> GovernanceRuleOut:
    # Validate rule_type against the runtime's KNOWN_RULE_TYPES at write
    # time, and validate the FULL resulting constitution actually compiles
    # before committing — a bad rule is never persisted.
    proposed = GovernanceRule(
        workspace_id=ctx.workspace_id,
        name=payload.name,
        rule_type=payload.rule_type,
        config=payload.config,
        enabled=payload.enabled,
    )
    capabilities = _load_capabilities(db, ctx.workspace_id)
    existing_rules = _load_rules(db, ctx.workspace_id)
    try:
        compile_constitution(
            ctx.workspace, capabilities, existing_rules + [proposed]
        )
    except GovernanceConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    db.add(proposed)
    db.commit()
    db.refresh(proposed)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.GOVERNANCE_RULE_CREATED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="governance_rule",
        resource_id=proposed.id,
        actor_user_id=ctx.user.id,
        metadata={"name": proposed.name, "rule_type": proposed.rule_type},
    )
    db.commit()

    return GovernanceRuleOut.from_model(proposed)


@router.patch("/rules/{rule_id}", response_model=GovernanceRuleOut)
def update_rule(
    rule_id: str,
    payload: GovernanceRuleUpdate,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> GovernanceRuleOut:
    rule = _load_rule(db, ctx, rule_id)

    # Build the proposed rule state and validate the full constitution.
    proposed = GovernanceRule(
        workspace_id=rule.workspace_id,
        name=payload.name if payload.name is not None else rule.name,
        rule_type=rule.rule_type,
        config=payload.config if payload.config is not None else rule.config,
        enabled=payload.enabled if payload.enabled is not None else rule.enabled,
    )
    capabilities = _load_capabilities(db, ctx.workspace_id)
    other_rules = [
        r for r in _load_rules(db, ctx.workspace_id) if r.id != rule.id
    ]
    try:
        compile_constitution(
            ctx.workspace, capabilities, other_rules + [proposed]
        )
    except GovernanceConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if payload.name is not None:
        rule.name = payload.name
    if payload.config is not None:
        rule.config = payload.config
    if payload.enabled is not None:
        rule.enabled = payload.enabled

    db.commit()
    db.refresh(rule)

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.GOVERNANCE_RULE_UPDATED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="governance_rule",
        resource_id=rule.id,
        actor_user_id=ctx.user.id,
        metadata={"name": rule.name, "rule_type": rule.rule_type, "enabled": rule.enabled},
    )
    db.commit()

    return GovernanceRuleOut.from_model(rule)


@router.delete("/rules/{rule_id}", response_model=MessageResponse)
def delete_rule(
    rule_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    rule = _load_rule(db, ctx, rule_id)
    rule_id_val, rule_name, rule_type = rule.id, rule.name, rule.rule_type
    db.delete(rule)
    db.commit()

    audit_service.record(
        db,
        ctx.workspace,
        event_type=AuditEventType.GOVERNANCE_RULE_DELETED,
        outcome=AuditOutcome.SUCCESS,
        resource_type="governance_rule",
        resource_id=rule_id_val,
        actor_user_id=ctx.user.id,
        metadata={"name": rule_name, "rule_type": rule_type},
    )
    db.commit()

    return MessageResponse(message="Rule deleted")


# ---------------------------------------------------------------------------
# Read-only preview / simulate
# ---------------------------------------------------------------------------


@router.get("/preview", response_model=GovernancePreview)
def preview_constitution(
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_READ)),
    db: DbSession = Depends(get_db),
) -> GovernancePreview:
    """What the workspace's constitution actually enforces right now.

    Built from the COMPILED constitution, not the raw rows, so the dashboard
    shows what is enforced, not what someone intended to configure.
    """
    capabilities = _load_capabilities(db, ctx.workspace_id)
    rules = _load_rules(db, ctx.workspace_id)
    compiled = compile_constitution(ctx.workspace, capabilities, rules)
    return GovernancePreview(**compiled.describe())


@router.post("/simulate", response_model=SimulateResponse)
def simulate_action(
    payload: SimulateRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.GOVERNANCE_READ)),
    db: DbSession = Depends(get_db),
) -> SimulateResponse:
    """Preview whether an action would be allowed — side-effect free.

    Calls ONLY GovernanceGate.check(), never Broker.request() (which would
    consume quota) and never Executor.execute() (which would produce real
    side effects). The gate verifies but does not consume approvals.
    """
    capabilities = _load_capabilities(db, ctx.workspace_id)
    rules = _load_rules(db, ctx.workspace_id)
    compiled = compile_constitution(ctx.workspace, capabilities, rules)

    action = Action(
        type=payload.type,
        capability=payload.capability,
        params=payload.params,
        amount=payload.amount,
    )
    gate = GovernanceGate(compiled.constitution)
    result = gate.check(action)
    return SimulateResponse(allowed=result.allowed, reason=result.reason)