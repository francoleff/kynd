"""THE canonical execution path.

Every action in the entire product goes through `execute_action` in this file.
There is exactly one call to `Executor.execute()` in the SaaS codebase and it
is here — `test_runtime_adapter.py` asserts that by scanning the source, so a
second path cannot be added quietly.

What this function does NOT do: decide anything. It assembles the workspace's
constitution, registry, and store, hands them to the runtime, and translates
the runtime's verdict into an HTTP-shaped result. Every allow/deny decision
belongs to the runtime.

Mission rule 0: "The SaaS layer must call into the existing deterministic
runtime." Not reimplement it, not second-guess it, not pre-filter it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from kynd_runtime import (
    Constitution,
    Executor,
    KyndConcurrentExecutionError,
    KyndExecutionError,
    SqliteStore,
    ToolNotFoundError,
    ToolRegistry,
)
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import GovernanceRule, Integration, Workspace, WorkspaceCapability
from ..runtime.constitution_compiler import (
    CompiledConstitution,
    GovernanceConfigError,
    compile_constitution,
)
from ..runtime.registry_factory import (
    CredentialInParamsError,
    assert_no_credentials,
    build_registry,
)
from ..runtime.store_factory import get_store

logger = logging.getLogger(__name__)


class ExecutionOutcome(str):
    """String enum of what happened, for the API and the UI."""

    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    FAILED = "FAILED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    CONFIG_ERROR = "CONFIG_ERROR"


@dataclass
class ExecutionResult:
    """The result of one governed action.

    `outcome` is what the customer sees. `reason` comes from the runtime and
    is derived from the customer's own constitution, so it is safe and useful
    to display — unlike an internal exception, which is not.
    """

    outcome: str
    reason: str
    result: Any = None
    capability: str | None = None
    action_type: str | None = None

    @property
    def executed(self) -> bool:
        return self.outcome == ExecutionOutcome.EXECUTED


@dataclass
class WorkspaceRuntime:
    """Everything needed to run one governed action for one workspace."""

    constitution: Constitution
    compiled: CompiledConstitution
    registry: ToolRegistry
    store: SqliteStore
    executor: Executor


def load_workspace_runtime(
    db: DbSession,
    workspace: Workspace,
    handler_factory: Callable[[Integration, str], Callable[[dict[str, Any]], Any]],
) -> WorkspaceRuntime:
    """Assemble the runtime for a workspace from its stored configuration.

    Built per request (0.601 ms, measured in the Phase 0 audit). A cache would
    have to be invalidated on every governance edit, and enforcing yesterday's
    rules is a far worse failure than spending 0.6 ms.
    """
    capabilities = (
        db.execute(
            select(WorkspaceCapability).where(
                WorkspaceCapability.workspace_id == workspace.id
            )
        )
        .scalars()
        .all()
    )
    rules = (
        db.execute(
            select(GovernanceRule).where(GovernanceRule.workspace_id == workspace.id)
        )
        .scalars()
        .all()
    )
    integrations = (
        db.execute(select(Integration).where(Integration.workspace_id == workspace.id))
        .scalars()
        .all()
    )

    compiled = compile_constitution(workspace, list(capabilities), list(rules))
    registry = build_registry(list(capabilities), list(integrations), handler_factory)
    store = get_store(workspace.id)

    executor = Executor(compiled.constitution, registry, store=store)

    return WorkspaceRuntime(
        constitution=compiled.constitution,
        compiled=compiled,
        registry=registry,
        store=store,
        executor=executor,
    )


def execute_action(
    db: DbSession,
    workspace: Workspace,
    capability: str,
    params: dict[str, Any],
    handler_factory: Callable[[Integration, str], Callable[[dict[str, Any]], Any]],
    action_type: str | None = None,
    approval_id: str | None = None,
    idempotency_key: str | None = None,
) -> ExecutionResult:
    """Run one action through the full governance pipeline.

    `approval_id` is injected HERE, server-side, by the approval service after
    a human decision. It is deliberately a separate argument rather than a
    params key, so a caller (including a model-driven one) cannot smuggle a
    forged approval in with the business arguments. See audit finding S-4.
    """
    try:
        # Fail before anything is recorded, and before quota is touched.
        assert_no_credentials(params)
    except CredentialInParamsError as exc:
        logger.warning(
            "rejected action with credential-shaped params workspace=%s capability=%s",
            workspace.id,
            capability,
        )
        return ExecutionResult(
            outcome=ExecutionOutcome.BLOCKED,
            reason=str(exc),
            capability=capability,
            action_type=action_type,
        )

    try:
        runtime = load_workspace_runtime(db, workspace, handler_factory)
    except GovernanceConfigError as exc:
        # The workspace's own configuration is invalid. Say so plainly — this
        # is fixable by the customer, unlike an internal error.
        return ExecutionResult(
            outcome=ExecutionOutcome.CONFIG_ERROR,
            reason=str(exc),
            capability=capability,
            action_type=action_type,
        )

    call_params = dict(params)
    if approval_id is not None:
        call_params["approval_id"] = approval_id
    if idempotency_key is not None:
        call_params["idempotency_key"] = idempotency_key

    try:
        result = runtime.executor.execute(
            capability, call_params, action_type=action_type
        )
    except KyndExecutionError as exc:
        # A governance denial. The message is derived from the customer's own
        # constitution, so it is meaningful to them and safe to return.
        reason = str(exc)
        outcome = (
            ExecutionOutcome.APPROVAL_REQUIRED
            if _is_approval_denial(reason)
            else ExecutionOutcome.BLOCKED
        )
        logger.info(
            "action denied workspace=%s capability=%s outcome=%s",
            workspace.id,
            capability,
            outcome,
        )
        return ExecutionResult(
            outcome=outcome,
            reason=reason,
            capability=capability,
            action_type=action_type,
        )
    except ToolNotFoundError:
        return ExecutionResult(
            outcome=ExecutionOutcome.NOT_AVAILABLE,
            reason=(
                f"No connected integration provides '{capability}'. Connect the "
                f"integration, or enable the capability in your settings."
            ),
            capability=capability,
            action_type=action_type,
        )
    except KyndConcurrentExecutionError as exc:
        return ExecutionResult(
            outcome=ExecutionOutcome.FAILED,
            reason=str(exc),
            capability=capability,
            action_type=action_type,
        )
    except Exception:
        # The integration itself failed. Governance ALLOWED this action, and
        # the runtime has already recorded that distinction in its execution
        # log — an audit reader must be able to tell a permitted-but-failed
        # action from a blocked one. The detail stays server-side.
        logger.exception(
            "integration failure workspace=%s capability=%s", workspace.id, capability
        )
        return ExecutionResult(
            outcome=ExecutionOutcome.FAILED,
            reason="The action was permitted but the integration failed to complete it.",
            capability=capability,
            action_type=action_type,
        )

    return ExecutionResult(
        outcome=ExecutionOutcome.EXECUTED,
        reason="Executed successfully",
        result=result,
        capability=capability,
        action_type=action_type,
    )


def _is_approval_denial(reason: str) -> bool:
    """Whether a denial was specifically about a missing/invalid approval.

    Used only to choose which message the UI shows ("needs approval" vs
    "blocked"). It never changes the decision — the runtime already denied the
    action either way, and this function runs after that denial.
    """
    lowered = reason.lower()
    return "approval" in lowered
