"""Request/response schemas.

Every API boundary is an explicit Pydantic model. No SQLAlchemy object is ever
returned directly (mission section 19), because that leaks columns — including
`password_hash` — the moment someone adds one.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from ..models import GovernanceRule, Role, WorkspaceCapability

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """A lowercase, hyphenated, URL-safe slug. Never empty."""
    slug = _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")
    return slug[:60] or "workspace"


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    name: str | None = Field(default=None, max_length=200)
    workspace_name: str = Field(min_length=1, max_length=200)

    @field_validator("workspace_name", "name")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=256)


class UserOut(BaseModel):
    """A user as the API describes them. Note what is absent: password_hash."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str | None
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_model(cls, user) -> "UserOut":  # noqa: ANN001 - avoids a circular import
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified_at is not None,
            created_at=user.created_at,
        )


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    onboarding_completed: bool
    created_at: datetime

    @classmethod
    def from_model(cls, workspace) -> "WorkspaceOut":  # noqa: ANN001
        return cls(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            onboarding_completed=workspace.onboarding_completed_at is not None,
            created_at=workspace.created_at,
        )


class MembershipOut(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    role: Role
    email: str
    name: str | None
    created_at: datetime


class WorkspaceSummary(BaseModel):
    """A workspace plus the caller's own role in it."""

    id: str
    name: str
    slug: str
    role: Role


class MeResponse(BaseModel):
    user: UserOut
    workspaces: list[WorkspaceSummary]
    current_workspace: WorkspaceOut | None = None
    role: Role | None = None
    permissions: list[str] = Field(default_factory=list)


class AuthResponse(BaseModel):
    user: UserOut
    workspace: WorkspaceOut
    role: Role


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    """The single customer-facing error shape.

    `error_id` is a correlation handle a customer can quote in a support
    request; the stack trace it maps to stays server-side (mission section 32).
    """

    detail: str
    error_id: str | None = None


# ---------------------------------------------------------------------------
# Governance: WorkspaceCapability
# ---------------------------------------------------------------------------

class WorkspaceCapabilityBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    enabled: bool = True
    max_amount: float | None = None
    max_calls_per_day: int | None = None
    allowed_targets: list[str] | None = None
    requires_approval: bool = False


class WorkspaceCapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    integration_id: str | None
    name: str
    enabled: bool
    max_amount: float | None
    max_calls_per_day: int | None
    allowed_targets: list[str] | None
    requires_approval: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, cap: WorkspaceCapability) -> "WorkspaceCapabilityOut":
        return cls(
            id=cap.id,
            workspace_id=cap.workspace_id,
            integration_id=cap.integration_id,
            name=cap.name,
            enabled=cap.enabled,
            max_amount=cap.max_amount,
            max_calls_per_day=cap.max_calls_per_day,
            allowed_targets=cap.allowed_targets,
            requires_approval=cap.requires_approval,
            created_at=cap.created_at,
            updated_at=cap.updated_at,
        )


class WorkspaceCapabilityUpdate(BaseModel):
    enabled: bool | None = None
    max_amount: float | None = None
    max_calls_per_day: int | None = None
    allowed_targets: list[str] | None = None
    requires_approval: bool | None = None


# ---------------------------------------------------------------------------
# Governance: GovernanceRule
# ---------------------------------------------------------------------------

class GovernanceRuleBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    rule_type: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)
    enabled: bool = True


class GovernanceRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    name: str
    rule_type: str
    config: dict
    enabled: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, rule: GovernanceRule) -> "GovernanceRuleOut":
        return cls(
            id=rule.id,
            workspace_id=rule.workspace_id,
            name=rule.name,
            rule_type=rule.rule_type,
            config=rule.config,
            enabled=rule.enabled,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
        )


class GovernanceRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict | None = None
    enabled: bool | None = None


# ---------------------------------------------------------------------------
# Governance: preview + simulate
# ---------------------------------------------------------------------------

class GovernancePreview(BaseModel):
    """UI-safe summary of what Kynd can do, cannot do, and must ask about."""

    allowed: list[str]
    blocked_capabilities: list[str]
    blocked_action_types: list[str]
    approval_required: list[str]
    limits: dict[str, dict]


class SimulateRequest(BaseModel):
    """An action to preview — would the gate allow it?"""

    type: str = Field(min_length=1, max_length=128)
    capability: str = Field(min_length=1, max_length=128)
    params: dict = Field(default_factory=dict)
    amount: float | None = None


class SimulateResponse(BaseModel):
    allowed: bool
    reason: str


class ApprovalRequestCreate(BaseModel):
    capability: str = Field(min_length=1, max_length=128)
    action_type: str | None = Field(default=None, max_length=128)
    target: str | None = Field(default=None, max_length=200)
    amount: float | None = None
    params: dict = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=2000)


class ApprovalDecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ExecuteApprovalRequest(BaseModel):
    """Optional idempotency override for POST /approvals/{id}/execute.

    Almost always omitted — approval_service.execute_approved_request
    already defaults to a key derived from the request's own id, so calling
    execute twice on the same request cannot double-run it even without
    this. Exists for a caller (e.g. a retry-safe automation) that wants its
    own explicit key.
    """

    idempotency_key: str | None = Field(default=None, max_length=200)


class ExecutionOutcomeOut(BaseModel):
    """What happened when an approved request was actually run."""

    outcome: str
    reason: str
    result: object = None


class ApprovalRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    capability: str
    action_type: str | None
    target: str | None
    amount: float | None
    params: dict
    reason: str | None
    status: str
    requested_by_user_id: str | None
    decided_by_user_id: str | None
    decided_at: datetime | None
    decision_note: str | None
    executed_at: datetime | None = None
    execution_outcome: str | None = None
    execution_reason: str | None = None
    expires_at: datetime
    created_at: datetime

    @classmethod
    def from_model(cls, request) -> "ApprovalRequestOut":  # noqa: ANN001
        return cls(
            id=request.id,
            workspace_id=request.workspace_id,
            capability=request.capability,
            action_type=request.action_type,
            target=request.target,
            amount=request.amount,
            params=request.params or {},
            reason=request.reason,
            status=request.status.value,
            requested_by_user_id=request.requested_by_user_id,
            decided_by_user_id=request.decided_by_user_id,
            decided_at=request.decided_at,
            decision_note=request.decision_note,
            executed_at=request.executed_at,
            execution_outcome=request.execution_outcome,
            execution_reason=request.execution_reason,
            expires_at=request.expires_at,
            created_at=request.created_at,
        )


class ExecutionRecordOut(BaseModel):
    """One row from the runtime's own `execution_log`, shaped for the UI.

    Built directly from the runtime store's dict output — there is no ORM
    model for this, deliberately: the runtime's SQLite store is the source of
    truth (audit section 3.2), and this schema is a read-only translation of
    it, not a second copy of the data.
    """

    id: int
    ts: float
    capability: str
    action_type: str | None
    outcome: str
    reason: str
    idempotency_key: str | None = None
    error: str | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    event_type: str
    outcome: str
    actor_user_id: str | None
    resource_type: str
    resource_id: str | None
    metadata: dict
    runtime_execution_id: int | None
    approval_request_id: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, event) -> "AuditEventOut":  # noqa: ANN001
        return cls(
            id=event.id,
            workspace_id=event.workspace_id,
            event_type=event.event_type.value,
            outcome=event.outcome.value,
            actor_user_id=event.actor_user_id,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            metadata=event.event_metadata or {},
            runtime_execution_id=event.runtime_execution_id,
            approval_request_id=event.approval_request_id,
            created_at=event.created_at,
        )


class SlackConnectRequest(BaseModel):
    """What an authenticated Kynd user submits to connect Slack.

    `bot_token` never appears in any response schema — see
    SlackIntegrationOut below, which carries only the masked hint.
    """

    bot_token: str = Field(min_length=1, max_length=4096)
    team_id: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)


class SlackIntegrationOut(BaseModel):
    """The Slack integration as the UI is allowed to see it.

    No `bot_token`, no ciphertext, no key id — only `credential_hint`
    (e.g. "xoxb-...4f2a"), same masking rule as every other credential in
    this codebase (kynd_api/security/crypto.py `mask`).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    status: str
    display_name: str
    team_id: str | None
    credential_hint: str | None
    connected_at: datetime
    last_tested_at: datetime | None
    last_error: str | None

    @classmethod
    def from_model(cls, integration) -> "SlackIntegrationOut":  # noqa: ANN001
        return cls(
            id=integration.id,
            workspace_id=integration.workspace_id,
            status=integration.status.value,
            display_name=integration.display_name,
            team_id=integration.external_id,
            credential_hint=integration.credential_hint,
            connected_at=integration.connected_at,
            last_tested_at=integration.last_tested_at,
            last_error=integration.last_error,
        )


class SlackTestResult(BaseModel):
    ok: bool
    error: str | None = None


class ProposalGenerateRequest(BaseModel):
    """What an authenticated Kynd user submits to generate an AI proposal.

    `hints` lets the caller (or a future real integration) supply structured
    fields directly — the StaticAIProvider in Phase 10 reads capability/
    action_type/target/amount/params straight from here. A real model
    provider in a later phase would instead derive these from `intent`
    alone; the schema stays the same either way.
    """

    intent: str = Field(min_length=1, max_length=4000)
    hints: dict = Field(default_factory=dict)


class AIProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    intent: str
    capability: str | None
    action_type: str | None
    target: str | None
    amount: float | None
    params: dict
    status: str
    rejection_reason: str | None
    approval_request_id: str | None
    created_by_user_id: str | None
    created_at: datetime

    @classmethod
    def from_model(cls, proposal) -> "AIProposalOut":  # noqa: ANN001
        return cls(
            id=proposal.id,
            workspace_id=proposal.workspace_id,
            intent=proposal.intent,
            capability=proposal.capability,
            action_type=proposal.action_type,
            target=proposal.target,
            amount=proposal.amount,
            params=proposal.params or {},
            status=proposal.status.value,
            rejection_reason=proposal.rejection_reason,
            approval_request_id=proposal.approval_request_id,
            created_by_user_id=proposal.created_by_user_id,
            created_at=proposal.created_at,
        )
