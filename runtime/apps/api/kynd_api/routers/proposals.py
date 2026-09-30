"""AI proposal routes — authenticated, tenant-scoped.

`POST /proposals/generate` is the ONLY write endpoint: it runs a context
through ai_proposal_service.generate_proposal and returns whatever the
pipeline decided (REJECTED or ROUTED_TO_APPROVAL — see that module's
docstring). There is no `/proposals/{id}/approve` here; a routed proposal's
approval_request_id points at a real ApprovalRequest, decided through the
EXISTING Approval Center (`POST /approvals/{id}/approve`) — this router
does not duplicate that surface.

Permissions reuse the existing matrix: `ACTION_PROPOSE` to generate (same
permission a human already needs to file a manual approval request),
`APPROVAL_READ` to list/read (a proposal IS a candidate approval request —
same visibility rule).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..ai.provider import ProposalContext, StaticAIProvider
from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import AIProposal, AIProposalStatus, AuditEventType, AuditOutcome
from ..schemas import AIProposalOut, ProposalGenerateRequest
from ..security.permissions import Permission
from ..services import ai_proposal_service, audit_service

router = APIRouter(prefix="/proposals", tags=["proposals"])

# One process-wide static provider for Phase 10. Stateless and
# credential-free (see ai/provider.py) — safe to share across requests, and
# swapping it for a real model provider later is a one-line change here,
# nothing downstream.
_PROVIDER = StaticAIProvider()


@router.post("/generate", response_model=AIProposalOut, status_code=status.HTTP_201_CREATED)
def generate_proposal(
    payload: ProposalGenerateRequest,
    ctx: WorkspaceContext = Depends(require_permission(Permission.ACTION_PROPOSE)),
    db: DbSession = Depends(get_db),
) -> AIProposalOut:
    outcome = ai_proposal_service.generate_proposal(
        db,
        ctx.workspace,
        provider=_PROVIDER,
        context=ProposalContext(intent=payload.intent, hints=payload.hints),
        created_by_user_id=ctx.user.id,
    )
    db.commit()
    db.refresh(outcome.proposal)

    if outcome.proposal.status == AIProposalStatus.REJECTED:
        audit_service.record(
            db,
            ctx.workspace,
            event_type=AuditEventType.AI_PROPOSAL_REJECTED,
            outcome=AuditOutcome.DENIED,
            resource_type="ai_proposal",
            resource_id=outcome.proposal.id,
            actor_user_id=ctx.user.id,
            metadata={
                "capability": outcome.proposal.capability,
                "reason": outcome.proposal.rejection_reason,
            },
        )
    else:
        audit_service.record(
            db,
            ctx.workspace,
            event_type=AuditEventType.AI_PROPOSAL_ROUTED_TO_APPROVAL,
            outcome=AuditOutcome.SUCCESS,
            resource_type="ai_proposal",
            resource_id=outcome.proposal.id,
            actor_user_id=ctx.user.id,
            metadata={"capability": outcome.proposal.capability},
            approval_request_id=outcome.approval_request_id,
        )
    db.commit()

    return AIProposalOut.from_model(outcome.proposal)


@router.get("", response_model=list[AIProposalOut])
def list_proposals(
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_READ)),
    db: DbSession = Depends(get_db),
) -> list[AIProposalOut]:
    rows = (
        db.execute(
            select(AIProposal)
            .where(AIProposal.workspace_id == ctx.workspace_id)
            .order_by(AIProposal.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [AIProposalOut.from_model(row) for row in rows]


@router.get("/{proposal_id}", response_model=AIProposalOut)
def get_proposal(
    proposal_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.APPROVAL_READ)),
    db: DbSession = Depends(get_db),
) -> AIProposalOut:
    proposal = db.execute(
        select(AIProposal).where(
            AIProposal.id == proposal_id,
            AIProposal.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return AIProposalOut.from_model(proposal)
