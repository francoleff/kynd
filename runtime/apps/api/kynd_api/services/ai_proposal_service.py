"""AI proposal pipeline.

USER / EVENT -> AI (untrusted) -> STRUCTURED VALIDATION -> GOVERNANCE PREVIEW
-> ApprovalRequest (never auto-approved, never executed) -> AUDIT.

Two rules this module exists to enforce, on top of what the runtime already
enforces:

1. This is not a second Executor. Nothing here calls `Executor.execute()` or
   `Broker.request()`. The ONLY runtime primitive touched is
   `GovernanceGate.check()` — read-only, side-effect free (Phase 0 audit
   probe 5) — used purely to pre-screen a proposal before it becomes an
   approval request. A hard-blocked proposal is rejected outright rather
   than filed for a human to reject manually; a proposal that passes the
   gate is filed as an approval request regardless of whether the
   capability itself requires approval — AI-originated actions ALWAYS route
   through a human, never straight to execution.

2. Untrusted input, checked structurally. `RawProposal` (ai/provider.py) has
   no `approval_id` field at all. Every OTHER field is independently
   revalidated here: capability must exist and be enabled in the workspace,
   amount must be non-negative and finite, params must pass the same
   `assert_no_credentials` boundary every other action does. A malformed or
   hostile provider output fails at THIS layer, before it is ever compiled
   into a runtime Action.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from kynd_runtime import Action, GovernanceGate
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..ai.provider import AIProvider, AIProviderError, ProposalContext, RawProposal
from ..models import AIProposal, AIProposalStatus, GovernanceRule, Workspace, WorkspaceCapability
from ..runtime.constitution_compiler import compile_constitution
from ..runtime.registry_factory import CredentialInParamsError, assert_no_credentials
from ..services import approval_service
from ..services.approval_service import ApprovalServiceError


class ProposalValidationError(Exception):
    """A proposal failed structural validation before governance was even
    consulted. Distinct from a governance denial — this is a shape/schema
    problem with the proposal itself."""


@dataclass
class ProposalOutcome:
    """What happened to one AI proposal."""

    proposal: AIProposal
    approval_request_id: str | None


def _load_capabilities_and_rules(
    db: DbSession, workspace: Workspace
) -> tuple[list[WorkspaceCapability], list[GovernanceRule]]:
    """Same query pattern execution_service.load_workspace_runtime uses —
    each service loads its own rows rather than sharing a cached copy, since
    a governance edit must be visible on the very next read (Phase 0 audit:
    built per request, ~0.6ms, cheaper than a stale-cache bug)."""
    capabilities = (
        db.execute(
            select(WorkspaceCapability).where(WorkspaceCapability.workspace_id == workspace.id)
        )
        .scalars()
        .all()
    )
    rules = (
        db.execute(select(GovernanceRule).where(GovernanceRule.workspace_id == workspace.id))
        .scalars()
        .all()
    )
    return list(capabilities), list(rules)


# Fields no proposal may ever carry, checked BEFORE anything else. Mirrors
# the runtime's own credential-in-params boundary — see
# registry_factory.assert_no_credentials — plus the one field that is
# structurally impossible for RawProposal to carry (approval_id) but is
# still checked here in case params itself smuggles one, since Slack/user
# input flows into `params` freely.
FORBIDDEN_PARAM_KEYS = frozenset({"approval_id", "runtime_approval_id"})


def _validate_raw_proposal(raw: RawProposal) -> None:
    if not raw.capability or not raw.capability.strip():
        raise ProposalValidationError("Proposal has no capability")

    if raw.amount is not None:
        if not isinstance(raw.amount, (int, float)) or isinstance(raw.amount, bool):
            raise ProposalValidationError("amount must be numeric")
        if math.isnan(raw.amount) or math.isinf(raw.amount):
            raise ProposalValidationError("amount must be a finite number")
        if raw.amount < 0:
            raise ProposalValidationError("amount must not be negative")

    if not isinstance(raw.params, dict):
        raise ProposalValidationError("params must be an object")

    for key in raw.params:
        if str(key).strip().lower() in FORBIDDEN_PARAM_KEYS:
            raise ProposalValidationError(
                f"Proposal params contain a forbidden key: {key!r}. An AI "
                f"proposal can never carry an approval token."
            )

    try:
        assert_no_credentials(raw.params)
    except CredentialInParamsError as exc:
        raise ProposalValidationError(str(exc)) from exc


def generate_proposal(
    db,
    workspace: Workspace,
    *,
    provider: AIProvider,
    context: ProposalContext,
    created_by_user_id: str | None,
) -> ProposalOutcome:
    """Run one context through the full proposal pipeline.

    Returns a ProposalOutcome whose `proposal.status` tells the caller what
    happened: REJECTED (structural or governance failure, nothing filed) or
    ROUTED_TO_APPROVAL (a real ApprovalRequest now exists, id in
    `approval_request_id`). Never EXECUTED — this pipeline cannot produce
    that outcome; only Phase 3's ExecutionService, acting on an
    ALREADY-APPROVED request, can.
    """
    try:
        raw = provider.propose(context)
    except AIProviderError as exc:
        proposal = AIProposal(
            workspace_id=workspace.id,
            intent=context.intent,
            capability=None,
            action_type=None,
            target=None,
            amount=None,
            params={},
            status=AIProposalStatus.REJECTED,
            rejection_reason=str(exc),
            created_by_user_id=created_by_user_id,
        )
        db.add(proposal)
        db.flush()
        return ProposalOutcome(proposal=proposal, approval_request_id=None)

    try:
        _validate_raw_proposal(raw)
    except ProposalValidationError as exc:
        proposal = AIProposal(
            workspace_id=workspace.id,
            intent=context.intent,
            capability=raw.capability,
            action_type=raw.action_type,
            target=raw.target,
            amount=raw.amount,
            params={},  # never persist params that failed validation
            status=AIProposalStatus.REJECTED,
            rejection_reason=str(exc),
            created_by_user_id=created_by_user_id,
        )
        db.add(proposal)
        db.flush()
        return ProposalOutcome(proposal=proposal, approval_request_id=None)

    # Governance preview: read-only, side-effect free. Exactly the same
    # primitive /governance/simulate already uses (Phase 5) — no new
    # governance path, no second rule engine.
    capabilities, rules = _load_capabilities_and_rules(db, workspace)
    compiled = compile_constitution(workspace, capabilities, rules)

    action = Action(
        type=raw.action_type or "unknown",
        capability=raw.capability,
        params=raw.params,
        amount=raw.amount,
    )
    gate = GovernanceGate(compiled.constitution)
    result = gate.check(action)

    if not result.allowed:
        proposal = AIProposal(
            workspace_id=workspace.id,
            intent=context.intent,
            capability=raw.capability,
            action_type=raw.action_type,
            target=raw.target,
            amount=raw.amount,
            params=raw.params,
            status=AIProposalStatus.REJECTED,
            rejection_reason=result.reason,
            created_by_user_id=created_by_user_id,
        )
        db.add(proposal)
        db.flush()
        return ProposalOutcome(proposal=proposal, approval_request_id=None)

    # Passed structural validation and the governance preview. AI-originated
    # proposals ALWAYS route to a human — never straight to execution, even
    # for a capability that does not itself require approval. This is a
    # policy decision layered above the runtime's own rules, not a
    # replacement for them.
    try:
        approval_request = approval_service.create_request(
            db,
            workspace,
            capability=raw.capability,
            action_type=raw.action_type,
            target=raw.target,
            amount=raw.amount,
            params=raw.params,
            reason=f"AI proposal: {raw.reason}",
            requested_by_user_id=created_by_user_id,
        )
    except ApprovalServiceError as exc:
        proposal = AIProposal(
            workspace_id=workspace.id,
            intent=context.intent,
            capability=raw.capability,
            action_type=raw.action_type,
            target=raw.target,
            amount=raw.amount,
            params={},
            status=AIProposalStatus.REJECTED,
            rejection_reason=str(exc),
            created_by_user_id=created_by_user_id,
        )
        db.add(proposal)
        db.flush()
        return ProposalOutcome(proposal=proposal, approval_request_id=None)

    proposal = AIProposal(
        workspace_id=workspace.id,
        intent=context.intent,
        capability=raw.capability,
        action_type=raw.action_type,
        target=raw.target,
        amount=raw.amount,
        params=raw.params,
        status=AIProposalStatus.ROUTED_TO_APPROVAL,
        approval_request_id=approval_request.id,
        created_by_user_id=created_by_user_id,
    )
    db.add(proposal)
    db.flush()
    return ProposalOutcome(proposal=proposal, approval_request_id=approval_request.id)
