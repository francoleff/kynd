"""Build a ToolRegistry whose handlers already hold their own credentials.

THE credential rule, and the reason this module exists:

    Phase 0 probe 3 PROVED that every key in `params` is serialised verbatim
    into the runtime's `execution_log.params_json`. A Slack token passed as a
    param is written to durable storage in plaintext, forever.

    Therefore: a credential NEVER travels in `params`. Each handler is a
    closure created per request that has already resolved and decrypted its
    own credential. The action carries only capability, target, amount, and
    business arguments.

This is finding S-1 in the audit, and `test_credential_security.py` asserts it
against real execution rather than trusting this docstring.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from kynd_runtime import ToolRegistry

from ..models import Integration, IntegrationStatus, WorkspaceCapability

logger = logging.getLogger(__name__)

# Keys that must never appear in an action's params. Enforced, not documented:
# `assert_no_credentials` runs on every action before it reaches the runtime.
FORBIDDEN_PARAM_KEYS = frozenset(
    {
        "token",
        "api_key",
        "apikey",
        "secret",
        "password",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "access_token",
        "refresh_token",
        "bot_token",
        "slack_bot_token",
        "private_key",
        "client_secret",
    }
)


class CredentialInParamsError(Exception):
    """An action carried something credential-shaped in its params.

    Fail closed and loudly. This is not a warning: the runtime would persist
    the value verbatim, so allowing it through would write a customer's secret
    into a durable log that is also rendered in the audit UI.
    """


def assert_no_credentials(params: dict[str, Any]) -> None:
    """Raise if `params` contains anything credential-shaped.

    Checks key NAMES, not values: a value-based heuristic would both miss
    unknown token formats and false-positive on legitimate message text.
    """
    for key in params:
        normalized = str(key).strip().lower().replace("-", "_")
        if normalized in FORBIDDEN_PARAM_KEYS:
            raise CredentialInParamsError(
                f"Parameter '{key}' looks like a credential. Credentials are "
                f"resolved server-side from the connected integration and must "
                f"never be sent with an action — the runtime persists params "
                f"verbatim to its execution log."
            )


class ToolNotAvailable(Exception):
    """No connected integration provides this capability for this workspace."""


def build_registry(
    capabilities: list[WorkspaceCapability],
    integrations: list[Integration],
    handler_factory: Callable[[Integration, str], Callable[[dict[str, Any]], Any]],
) -> ToolRegistry:
    """Assemble the registry for one request.

    `handler_factory(integration, capability_name)` returns the closure that
    performs the real side effect. It is injected rather than imported so that
    tests can substitute a recording handler and assert on what actually
    reached the integration boundary — without that seam, "no credential was
    sent" could only be reviewed by eye.
    """
    registry = ToolRegistry()
    by_id = {integration.id: integration for integration in integrations}

    for capability in capabilities:
        if not capability.enabled:
            continue
        if capability.integration_id is None:
            continue

        integration = by_id.get(capability.integration_id)
        if integration is None:
            continue
        if integration.status != IntegrationStatus.CONNECTED:
            # A disconnected integration is simply absent from the registry, so
            # the runtime raises ToolNotFoundError. Registering a handler that
            # would fail at call time instead would consume the workspace's
            # daily quota on an action that never had a chance to work.
            logger.info(
                "capability %s skipped: integration %s is %s",
                capability.name,
                integration.id,
                integration.status.value,
            )
            continue

        registry.register(
            capability.name, handler_factory(integration, capability.name)
        )

    return registry
