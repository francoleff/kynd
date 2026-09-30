"""The Approval Center's real workflow.

Orchestration only. This module owns the Postgres *lifecycle* row
(`ApprovalRequest`): pending -> approved/rejected/expired -> executed. It
never decides whether an action is actually permitted to run — that is
`execution_service.execute_action`, the SaaS's one canonical call into the
runtime, which independently re-verifies the approval token this service
mints.

The one rule that matters here (mission section on approvals, audit S-4):

    The frontend saying "approved" must never become the runtime assuming an
    approval exists. On APPROVE, this service asks the RUNTIME's own
    SqliteStore to mint a real one-time token scoped to
    (capability, action_type, target, amount). That token — not this table —
    is what `Executor.execute()` actually verifies.

    APPROVE and EXECUTE are deliberately two separate steps. Approving means
    a human said yes; nothing runs yet. Executing calls the same canonical
    `execute_action` the runtime adapter already proves is the sole
    execution path — this module does not reimplement governance, does not
    construct an Executor, and does not decide allow/deny. It only decides
    WHEN to ask the runtime, and records what the runtime said.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import ApprovalRequest, ApprovalRequestStatus, Integration, Workspace, utcnow
from ..runtime.registry_factory import CredentialInParamsError, assert_no_credentials
from ..runtime.store_factory import get_store
from . import execution_service
from .execution_service import ExecutionOutcome, ExecutionResult

# How long a customer has to decide before a pending request goes stale.
# Independent of the runtime approval TTL (minted only at APPROVE time, below).
DEFAULT_REQUEST_TTL_SECONDS = 24 * 60 * 60

# How long the RUNTIME token is valid for once a human approves. Short: the
# execution is expected to happen immediately after approval, not sometime
# next week.
RUNTIME_APPROVAL_TTL_SECONDS = 300.0


class ApprovalServiceError(Exception):
    """A recoverable, customer-facing approval workflow error."""


class ApprovalNotFound(ApprovalServiceError):
    pass


class ApprovalNotPending(ApprovalServiceError):
    """The request is not in a state that can still be decided."""


class ApprovalExpired(ApprovalServiceError):
    pass


class ApprovalNotApproved(ApprovalServiceError):
    """The request has not been APPROVED (or has already been executed)."""


class ApprovalHasNoRuntimeToken(ApprovalServiceError):
    """An APPROVED request with no runtime_approval_id. Should be unreachable —
    approve_request always mints one — kept as an explicit fail-closed guard
    rather than passing None into execute_action, which would silently ask
    for approval verification with nothing to present."""


@dataclass
class ApprovalDecisionResult:
    request: ApprovalRequest
    runtime_approval_id: str | None


def _sync_expiry(request: ApprovalRequest) -> ApprovalRequest:
    """Flip a stale PENDING row to EXPIRED. Read-path lazy expiry.

    A cron-free approach: nothing has to sweep the table on a timer. Any read
    or decide touching an overdue PENDING row corrects it before the caller
    sees it, so `status` is always accurate at the moment it's read.
    """
    if request.status == ApprovalRequestStatus.PENDING and request.is_expired:
        request.status = ApprovalRequestStatus.EXPIRED
    return request


def create_request(
    db: DbSession,
    workspace: Workspace,
    *,
    capability: str,
    action_type: str | None,
    target: str | None,
    amount: float | None,
    params: dict[str, Any],
    reason: str | None,
    requested_by_user_id: str | None,
    ttl_seconds: int = DEFAULT_REQUEST_TTL_SECONDS,
) -> ApprovalRequest:
    """File a new approval request. Does not touch the runtime at all.

    `params` is stored for display (the "requested arguments" the mission
    asks for) — never a credential, so the same boundary the executor uses is
    enforced here too, before anything is written to Postgres.
    """
    try:
        assert_no_credentials(params)
    except CredentialInParamsError as exc:
        raise ApprovalServiceError(str(exc)) from exc

    request = ApprovalRequest(
        workspace_id=workspace.id,
        capability=capability,
        action_type=action_type,
        target=target,
        amount=amount,
        params=params,
        reason=reason,
        status=ApprovalRequestStatus.PENDING,
        requested_by_user_id=requested_by_user_id,
        expires_at=utcnow() + timedelta(seconds=ttl_seconds),
    )
    db.add(request)
    db.flush()
    return request


def list_requests(
    db: DbSession,
    workspace: Workspace,
    *,
    status_filter: ApprovalRequestStatus | None = None,
) -> list[ApprovalRequest]:
    """All requests for one workspace, newest first, expiry synced."""
    rows = (
        db.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.workspace_id == workspace.id)
            .order_by(ApprovalRequest.created_at.desc())
        )
        .scalars()
        .all()
    )
    for row in rows:
        _sync_expiry(row)
    if status_filter is not None:
        rows = [row for row in rows if row.status == status_filter]
    return list(rows)


def _load_request(db: DbSession, workspace: Workspace, request_id: str) -> ApprovalRequest:
    """Load one request, scoped to the workspace. The tenancy boundary here.

    A request id from another tenant simply does not match this WHERE clause,
    same 404-not-403 pattern as `workspace.py::_load_member` — a cross-tenant
    id must not be distinguishable from one that never existed.
    """
    request = db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == request_id,
            ApprovalRequest.workspace_id == workspace.id,
        )
    ).scalar_one_or_none()
    if request is None:
        raise ApprovalNotFound(f"Approval request {request_id!r} not found")
    return _sync_expiry(request)


def get_request(db: DbSession, workspace: Workspace, request_id: str) -> ApprovalRequest:
    return _load_request(db, workspace, request_id)


def approve_request(
    db: DbSession,
    workspace: Workspace,
    request_id: str,
    *,
    decided_by_user_id: str,
    note: str | None = None,
) -> ApprovalDecisionResult:
    """Approve a pending request and mint the real runtime token.

    This is the ONLY place a runtime approval is issued from a human decision.
    The token is scoped exactly to what was requested — capability, action
    type, target, amount — so it cannot later be replayed against a different
    action. `Executor.execute()` still independently re-verifies it; nothing
    here can make the runtime trust an approval it did not itself mint.
    """
    request = _load_request(db, workspace, request_id)

    if request.status == ApprovalRequestStatus.EXPIRED:
        raise ApprovalExpired(f"Approval request {request_id!r} has expired")
    if request.status != ApprovalRequestStatus.PENDING:
        raise ApprovalNotPending(
            f"Approval request {request_id!r} is {request.status.value}, not PENDING"
        )

    store = get_store(workspace.id)
    runtime_approval_id = store.issue_approval(
        capability=request.capability,
        action_type=request.action_type,
        max_amount=request.amount,
        target=request.target,
        ttl_seconds=RUNTIME_APPROVAL_TTL_SECONDS,
        max_uses=1,
        issued_by=decided_by_user_id,
    )

    request.status = ApprovalRequestStatus.APPROVED
    request.decided_by_user_id = decided_by_user_id
    request.decided_at = utcnow()
    request.decision_note = note
    request.runtime_approval_id = runtime_approval_id
    db.flush()

    return ApprovalDecisionResult(request=request, runtime_approval_id=runtime_approval_id)


def reject_request(
    db: DbSession,
    workspace: Workspace,
    request_id: str,
    *,
    decided_by_user_id: str,
    note: str | None = None,
) -> ApprovalRequest:
    """Reject a pending request. No runtime interaction — nothing to revoke,

    because nothing was ever minted for a request that was never approved.
    """
    request = _load_request(db, workspace, request_id)

    if request.status == ApprovalRequestStatus.EXPIRED:
        raise ApprovalExpired(f"Approval request {request_id!r} has expired")
    if request.status != ApprovalRequestStatus.PENDING:
        raise ApprovalNotPending(
            f"Approval request {request_id!r} is {request.status.value}, not PENDING"
        )

    request.status = ApprovalRequestStatus.REJECTED
    request.decided_by_user_id = decided_by_user_id
    request.decided_at = utcnow()
    request.decision_note = note
    db.flush()
    return request


def execute_approved_request(
    db: DbSession,
    workspace: Workspace,
    request_id: str,
    *,
    handler_factory: Callable[[Integration, str], Callable[[dict[str, Any]], Any]],
    idempotency_key: str | None = None,
) -> ExecutionResult:
    """Run an already-approved request through the canonical execute_action path.

    This is the ONLY function in the SaaS layer that redeems a runtime
    approval token. It does not construct an Executor, does not call
    GovernanceGate or Broker directly, and does not decide allow/deny —
    `execution_service.execute_action` (the same function
    `tests/test_runtime_adapter.py` proves is the sole execution path) does
    all of that. This function's entire job is: load the request scoped to
    THIS workspace (the tenancy boundary — a request id from another tenant
    simply does not match), confirm it is in a runnable state, then hand its
    exact stored capability/action_type/target/amount/params plus its own
    minted runtime_approval_id to execute_action.

    Idempotency: `idempotency_key` defaults to the approval request's own id
    if the caller supplies none, so calling this twice for the same request
    (a double-click, a retried request) cannot double-execute — the runtime's
    own idempotency ledger (proven in test_runtime_adapter.py) makes the
    second call return the first call's cached result rather than
    re-invoking the handler. This does not weaken or bypass that mechanism;
    it simply ensures a caller who doesn't think to supply a key still gets
    the protection for free.
    """
    request = _load_request(db, workspace, request_id)

    if request.status == ApprovalRequestStatus.EXPIRED:
        raise ApprovalExpired(f"Approval request {request_id!r} has expired")
    if request.status == ApprovalRequestStatus.EXECUTED:
        raise ApprovalNotApproved(
            f"Approval request {request_id!r} has already been executed"
        )
    if request.status != ApprovalRequestStatus.APPROVED:
        raise ApprovalNotApproved(
            f"Approval request {request_id!r} is {request.status.value}, "
            f"not APPROVED — it must be approved by a human before it can run"
        )
    if not request.runtime_approval_id:
        raise ApprovalHasNoRuntimeToken(
            f"Approval request {request_id!r} has no runtime approval token"
        )

    try:
        assert_no_credentials(request.params or {})
    except CredentialInParamsError as exc:
        raise ApprovalServiceError(str(exc)) from exc

    call_params = dict(request.params or {})
    if request.target is not None:
        call_params.setdefault("target", request.target)
    if request.amount is not None:
        call_params.setdefault("amount", request.amount)

    result = execution_service.execute_action(
        db,
        workspace,
        capability=request.capability,
        params=call_params,
        handler_factory=handler_factory,
        action_type=request.action_type,
        approval_id=request.runtime_approval_id,
        idempotency_key=idempotency_key or f"approval:{request.id}",
    )

    # Record what the runtime actually said, regardless of outcome. A request
    # whose execution was BLOCKED or FAILED must be visibly distinguishable
    # from one that never attempted execution at all (status stays APPROVED,
    # executed_at stays None) — that distinction is the whole point of a
    # separate executed_at/execution_outcome pair rather than overloading
    # `status`.
    request.executed_at = utcnow()
    request.execution_outcome = result.outcome
    request.execution_reason = result.reason
    if result.outcome == ExecutionOutcome.EXECUTED:
        request.status = ApprovalRequestStatus.EXECUTED
    db.flush()

    return result
