"""SaaS control-plane models.

These tables hold identity, tenancy, and product configuration. They do NOT
hold governance enforcement state — quota counters, approval tokens,
idempotency claims, and the audit log live in the runtime's per-workspace
SQLite store, which is the proven enforcement boundary. See
docs/saas/SAAS_ARCHITECTURE_AUDIT.md section 5.2.
"""

from __future__ import annotations

import enum
import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC now.

    Deliberately not `datetime.utcnow()`, which returns a NAIVE datetime that
    compares incorrectly against the timezone-aware values Postgres returns
    for TIMESTAMPTZ columns — a silent source of expiry checks that pass when
    they should fail.
    """
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """A collision-resistant, prefixed, URL-safe identifier.

    Prefixed so an id is self-describing in a log line or a bug report, and so
    a workspace id can never be mistaken for a user id in a query written by
    hand. 32 hex chars = 128 bits.
    """
    return f"{prefix}_{secrets.token_hex(16)}"


class Base(DeclarativeBase):
    pass


class Role(str, enum.Enum):
    """Workspace roles, ordered least to most privileged.

    Permissions are defined in security/permissions.py — this enum is only the
    vocabulary. Keeping the two separate means a permission question is
    answered by one table, not by conditionals scattered across routers.
    """

    VIEWER = "VIEWER"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"
    OWNER = "OWNER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("usr"))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Stored lowercase+stripped for uniqueness. Postgres is case-SENSITIVE on
    # text, so without this a second signup as "Franco@x.com" would create a
    # duplicate account for the same human being.
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["SessionToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately excludes password_hash. A repr ends up in logs and
        # tracebacks; a hash there is a gift to anyone reading them.
        return f"<User {self.id} {self.email_normalized}>"


class Workspace(Base):
    """A tenant. Every piece of customer data hangs off one of these."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ws"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)

    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    memberships: Mapped[list["Membership"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Workspace {self.id} {self.slug}>"


class Membership(Base):
    """A user's role within one workspace.

    This table IS the tenancy boundary. `get_workspace_context` resolves a
    request's workspace by looking up the authenticated user's membership —
    never from anything the client sent.
    """

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id", name="uq_membership_user_workspace"),
        Index("ix_membership_workspace_role", "workspace_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[Role] = mapped_column(
        Enum(Role, name="role", native_enum=True), nullable=False, default=Role.VIEWER
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="memberships")
    workspace: Mapped[Workspace] = relationship(back_populates="memberships")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Membership {self.user_id}@{self.workspace_id} {self.role.value}>"


class SessionToken(Base):
    """A server-side session.

    Only the SHA-256 of the token is stored. A database dump therefore does not
    hand an attacker a set of working sessions — the same reasoning the runtime
    applies to approval tokens. Server-side storage (rather than a JWT) is what
    makes logout and forced revocation real rather than advisory.
    """

    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_expires", "user_id", "expires_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ses"))
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Sliding idle expiry.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Hard ceiling regardless of activity — an indefinitely-refreshed session is
    # an indefinitely-valid stolen cookie.
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    def is_valid(self, now: datetime | None = None) -> bool:
        now = now or utcnow()
        if self.revoked_at is not None:
            return False
        if self.expires_at <= now:
            return False
        return self.absolute_expires_at > now

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Never includes token_hash.
        return f"<SessionToken {self.id} user={self.user_id}>"


class IntegrationProvider(str, enum.Enum):
    """Integrations the product supports. Small on purpose (mission section 11)."""

    SLACK = "SLACK"
    EMAIL = "EMAIL"


class IntegrationStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class Integration(Base):
    """A workspace's connection to an external system.

    The credential is stored ENCRYPTED in `credential_ciphertext` and is never
    serialised to any API response. `credential_hint` is the only thing the UI
    ever sees — a masked fragment such as "xoxb-...4f2a" that lets a human
    recognise which token is installed without the value being recoverable.
    """

    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_integration_workspace_provider"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("int"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[IntegrationProvider] = mapped_column(
        Enum(IntegrationProvider, name="integration_provider", native_enum=True), nullable=False
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        Enum(IntegrationStatus, name="integration_status", native_enum=True),
        nullable=False,
        default=IntegrationStatus.CONNECTED,
    )

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    credential_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    credential_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_hint: Mapped[str | None] = mapped_column(String(64), nullable=True)

    connected_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    workspace: Mapped[Workspace] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        # Deliberately excludes the ciphertext.
        return f"<Integration {self.id} {self.provider.value} ws={self.workspace_id}>"


class GovernanceRule(Base):
    """One governance rule, as configured by the customer in the UI.

    `rule_type` MUST be one of the four the runtime can actually enforce
    (KNOWN_RULE_TYPES in the runtime's constitution module). The compiler
    validates this, and a rule the runtime cannot enforce is never stored —
    otherwise the UI would display a safety rule that silently does nothing.
    """

    __tablename__ = "governance_rules"
    __table_args__ = (Index("ix_governance_rules_workspace_enabled", "workspace_id", "enabled"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rule"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # The rule's type-specific payload (action_types, capabilities, param, ...).
    # JSON because the shape genuinely differs per rule type; the compiler
    # validates each shape before it is ever used to make a decision.
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<GovernanceRule {self.id} {self.rule_type} ws={self.workspace_id}>"


class ApprovalRequestStatus(str, enum.Enum):
    """The lifecycle of a human approval request, as the customer sees it.

    This is the SaaS-layer *lifecycle*. The runtime's own `approvals` table
    (in the per-workspace SQLite store) holds the cryptographic *token* that
    is actually checked at execution time — this row exists so a customer can
    see and act on a request before that token is even minted. See
    docs/saas/SAAS_ARCHITECTURE_AUDIT.md section 1.4 and
    SAAS_IMPLEMENTATION_PLAN.md Phase 6.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    EXECUTED = "EXECUTED"


class ApprovalRequest(Base):
    """One human-in-the-loop approval request, Postgres side.

    On APPROVE, the approval service mints a real runtime approval token
    (`SqliteStore.issue_approval`, scoped to capability/action_type/target/
    amount) and stores its id in `runtime_approval_id` — purely for audit
    traceability. The runtime remains the sole arbiter of whether that token
    is still valid at execution time; this row is never consulted by the
    executor.
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("apr"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    capability: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Business arguments only — never a credential. The same
    # assert_no_credentials boundary applies here as at execution time.
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(ApprovalRequestStatus, name="approval_request_status", native_enum=True),
        nullable=False,
        default=ApprovalRequestStatus.PENDING,
    )

    requested_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Set once, at APPROVE time, from the runtime's own SqliteStore.issue_approval.
    # Traceability only — the runtime does not read this column.
    runtime_approval_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Set once, at the moment execute_action() actually runs this approved
    # request. Distinct from `status == APPROVED`: APPROVED means a human
    # said yes; EXECUTED means the runtime actually ran it. A request can be
    # APPROVED and never reach EXECUTED (the customer clicks Approve, then
    # never clicks Run) — see approval_service.execute_approved_request.
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    execution_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<ApprovalRequest {self.id} {self.status.value} ws={self.workspace_id}>"

    @property
    def is_expired(self) -> bool:
        """Whether this request's window has passed, independent of `status`.

        `status` is only updated to EXPIRED when something reads the row
        (list/decide) — a lazily-updated field would let an approve action
        race a request that expired a second ago. Callers must check both.
        """
        return utcnow() > self.expires_at


class WorkspaceCapability(Base):
    """A capability this workspace has enabled, with its limits.

    Compiles into the runtime constitution's `capabilities[]` entry:
    max_amount, max_calls_per_day, allowed_targets. `requires_approval` becomes
    a `require_param` + `verify: approval` hard rule scoped to this capability.
    """

    __tablename__ = "workspace_capabilities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_capability_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cap"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    integration_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("integrations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    max_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_calls_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # None means "no allowlist". An EMPTY list means "nothing is allowed" and is
    # a meaningfully different, stricter statement — the compiler preserves that
    # distinction rather than collapsing both to "unrestricted".
    allowed_targets: Mapped[list | None] = mapped_column(JSON, nullable=True)

    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<WorkspaceCapability {self.name} ws={self.workspace_id}>"


class AuditEventType(str, enum.Enum):
    """The closed vocabulary of things the Audit Center reports on.

    Deliberately closed, same reasoning as GovernanceRule.rule_type being
    checked against the runtime's KNOWN_RULE_TYPES: an audit trail with an
    open-ended, ad-hoc event name is not queryable or trustworthy. New event
    types are added here, explicitly, by whoever adds the action that causes
    them — never invented at the call site as a free-text string.
    """

    GOVERNANCE_RULE_CREATED = "governance_rule.created"
    GOVERNANCE_RULE_UPDATED = "governance_rule.updated"
    GOVERNANCE_RULE_DELETED = "governance_rule.deleted"
    CAPABILITY_CREATED = "capability.created"
    CAPABILITY_UPDATED = "capability.updated"
    CAPABILITY_DELETED = "capability.deleted"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_APPROVED = "approval.approved"
    APPROVAL_REJECTED = "approval.rejected"
    WORKSPACE_UPDATED = "workspace.updated"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_REMOVED = "member.removed"
    INTEGRATION_CONNECTED = "integration.connected"
    INTEGRATION_DISCONNECTED = "integration.disconnected"
    INTEGRATION_TEST_SUCCEEDED = "integration.test_succeeded"
    INTEGRATION_TEST_FAILED = "integration.test_failed"
    SLACK_EVENT_RECEIVED = "slack.event_received"
    SLACK_MESSAGE_SENT = "slack.message_sent"
    AI_PROPOSAL_REJECTED = "ai_proposal.rejected"
    AI_PROPOSAL_ROUTED_TO_APPROVAL = "ai_proposal.routed_to_approval"
    ACTION_EXECUTED = "action.executed"
    ACTION_BLOCKED = "action.blocked"
    ACTION_FAILED = "action.failed"


class AuditOutcome(str, enum.Enum):
    """What actually happened. Never fabricated — set only at the point a
    real committed change (or a real, meaningful denial) is known."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    ERROR = "ERROR"


class AuditEvent(Base):
    """A UI-facing record of a meaningful application action.

    This is NOT the runtime's execution_log or audit_log — those already
    exist, are proven, and live per-workspace in SQLite (see
    docs/saas/SAAS_ARCHITECTURE_AUDIT.md section 3.2; Phase 7's
    /executions reads them directly). This table is the SaaS control
    plane's OWN activity trail: who changed governance, who decided an
    approval, who touched team/workspace settings. Where an event
    corresponds to something the runtime already recorded, this row carries
    a REFERENCE (`runtime_execution_id` / `runtime_approval_id`) rather than
    a second copy of the runtime's data — traceable, not duplicated.

    Rows are written only at the point a real action is taken (inside the
    same request/transaction as the change itself, see audit_service.py) —
    never spun up as decorative or speculative logging.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_workspace_created", "workspace_id", "created_at"),
        Index("ix_audit_events_workspace_type", "workspace_id", "event_type"),
        Index("ix_audit_events_workspace_resource", "workspace_id", "resource_type", "resource_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("aud"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    event_type: Mapped[AuditEventType] = mapped_column(
        Enum(AuditEventType, name="audit_event_type", native_enum=True), nullable=False
    )
    outcome: Mapped[AuditOutcome] = mapped_column(
        Enum(AuditOutcome, name="audit_outcome", native_enum=True), nullable=False
    )

    # Who or what caused this. None for a system-caused event (there are
    # none yet, but the column must not force a fake actor into existence).
    actor_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # What was affected: a (type, id) pair, e.g. ("governance_rule", "rule_abc123").
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Small, non-secret context: a rule's name, an old/new role, a
    # capability's name. The same credential boundary the runtime enforces
    # applies here too — never a token, never a raw credential.
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Traceability, not duplication: a pointer into the runtime's own
    # per-workspace execution_log row id, or into this SaaS layer's
    # ApprovalRequest id, when the event corresponds to one.
    runtime_execution_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approval_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditEvent {self.id} {self.event_type.value} ws={self.workspace_id}>"


class AIProposalStatus(str, enum.Enum):
    """What happened to one AI-generated proposal.

    Deliberately has NO 'approved' or 'executed' member. This table records
    only what the proposal PIPELINE itself decided — reject outright, or
    route to a human via the Approval Center. Whatever a human later does
    with the resulting ApprovalRequest (approve/reject/expire) is recorded
    on THAT row (ApprovalRequestStatus), not duplicated here. Joining via
    `approval_request_id` gives the full picture without two tables trying
    to be the same source of truth.
    """

    REJECTED = "REJECTED"
    ROUTED_TO_APPROVAL = "ROUTED_TO_APPROVAL"


class AIProposal(Base):
    """One proposal an AI provider produced, and what the pipeline did with it.

    This is the AI proposal layer's own record — distinct from
    ApprovalRequest (Phase 6, which this table points into when a proposal
    is routed there) and distinct from the runtime's execution_log (which
    this table never touches; nothing here executes anything). See
    kynd_api/services/ai_proposal_service.py module docstring for the full
    pipeline this row is the artifact of.
    """

    __tablename__ = "ai_proposals"
    __table_args__ = (
        Index("ix_ai_proposals_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prop"))
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The free-text input the AI reasoned from (a Slack message, an operator
    # instruction). Never itself treated as authoritative — see
    # ai/provider.py.
    intent: Mapped[str] = mapped_column(Text, nullable=False)

    # What the provider proposed, after structural validation. None when
    # rejection happened before a capability could even be determined.
    capability: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Business arguments only — the same assert_no_credentials boundary the
    # runtime and the Approval Center both enforce applies here too, and a
    # proposal that FAILED validation never has its (possibly-hostile)
    # params persisted at all (see ai_proposal_service.py).
    params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[AIProposalStatus] = mapped_column(
        Enum(AIProposalStatus, name="ai_proposal_status", native_enum=True), nullable=False
    )
    # Populated only on REJECTED — the runtime's own governance-gate reason,
    # or a structural validation message. Never fabricated.
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Populated only on ROUTED_TO_APPROVAL. The proposal pipeline itself
    # never approves or executes anything past this point — see
    # ai_proposal_service.py.
    approval_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AIProposal {self.id} {self.status.value} ws={self.workspace_id}>"
