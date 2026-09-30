"""Production capability handlers — the real closures execution_service's
`handler_factory` argument builds, wired to real connected integrations.

Every handler here follows the exact rule registry_factory.py's module
docstring establishes: a credential never travels in an action's `params`
(the runtime persists params verbatim to its execution log). Instead, each
handler is a closure created per request that has ALREADY resolved and
decrypted its own integration's credential — the closure captures the
plaintext token in memory for the duration of one call, never returns it,
never logs it.

This module is intentionally thin. It answers exactly one question per
capability: "given a connected Integration row, what real side effect does
this capability name perform?" Today that is one answer (Slack
`chat.postMessage`, for any capability the customer has configured against a
connected Slack integration). Adding a new integration provider means adding
one more branch here — never touching execution_service.py, registry_factory.py,
or anything upstream of the ToolRegistry boundary.
"""

from __future__ import annotations

from typing import Any, Callable

from ..integrations import slack_client
from ..models import Integration, IntegrationProvider
from ..security import crypto


class HandlerConfigurationError(Exception):
    """A capability's connected integration cannot actually perform it.

    Raised INSIDE the handler closure, at call time — never at registry
    build time. registry_factory.build_registry already excludes a
    capability whose integration is not CONNECTED; this covers the residual
    case where the integration row itself is malformed (e.g. no stored
    credential) despite reporting CONNECTED, which must fail the one call
    rather than silently registering a handler that always raises.
    """


def production_handler_factory(
    integration: Integration, capability_name: str
) -> Callable[[dict[str, Any]], Any]:
    """The real `handler_factory` execution_service.load_workspace_runtime uses
    outside of tests.

    Resolves the credential ONCE per call (never cached across requests — a
    disconnect/reconnect between calls must take effect immediately, and
    holding a decrypted token in memory longer than one call widens the
    window an attacker with process memory access could exploit).
    """

    def handler(params: dict[str, Any]) -> Any:
        if integration.provider == IntegrationProvider.SLACK:
            return _slack_handler(integration, capability_name, params)
        raise HandlerConfigurationError(
            f"No production handler exists for integration provider "
            f"{integration.provider.value!r} (capability {capability_name!r})"
        )

    return handler


def _slack_handler(
    integration: Integration, capability_name: str, params: dict[str, Any]
) -> Any:
    if integration.credential_ciphertext is None or integration.credential_key_id is None:
        raise HandlerConfigurationError(
            f"Slack integration for capability {capability_name!r} has no "
            f"stored credential. Reconnect the integration."
        )

    token = crypto.decrypt_credential(
        integration.credential_ciphertext, integration.credential_key_id
    )

    target = params.get("target")
    if not isinstance(target, str) or not target:
        raise HandlerConfigurationError(
            f"Capability {capability_name!r} requires a 'target' channel"
        )
    text = params.get("text")
    if not isinstance(text, str) or not text:
        raise HandlerConfigurationError(
            f"Capability {capability_name!r} requires 'text' to send"
        )

    result = slack_client.post_message(token, channel=target, text=text)
    if not result.ok:
        # A real, un-fabricated failure. execute_action's own exception
        # handler turns this into ExecutionOutcome.FAILED without leaking
        # `result.error` verbatim to the customer beyond what execute_action
        # itself already decides is safe to show.
        raise RuntimeError(f"Slack chat.postMessage failed: {result.error}")

    return {"ok": True, "channel": target}
