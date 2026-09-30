"""Tool registry — maps capability names to callable implementations."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """Raised when a tool is not registered."""


class CapabilityAlreadyRegisteredError(Exception):
    """Raised when registering a capability that already has a handler.

    A silent override here is a silent capability hijack: a misconfigured
    import or a second `register()` call for the same name would otherwise
    replace a handler (e.g. `charge_card`) with no error and only a log line
    nobody reads. Registration must fail loudly by default; call sites that
    genuinely need to swap a handler (e.g. tests replacing a fixture handler)
    must say so explicitly with `replace=True`.
    """


class ToolRegistry:
    """Register and dispatch tool implementations by capability name.
    
    Usage:
        registry = ToolRegistry()
        registry.register("send_email", my_email_handler)
        result = registry.call("send_email", {"to": "user@example.com"})
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def register(
        self,
        capability: str,
        handler: Callable[[dict[str, Any]], Any],
        *,
        replace: bool = False,
    ) -> None:
        """Register a handler for a capability.

        Raises:
            CapabilityAlreadyRegisteredError: if `capability` already has a
                handler and `replace` is not explicitly set to True.
        """
        if capability in self._tools and not replace:
            raise CapabilityAlreadyRegisteredError(
                f"Capability '{capability}' is already registered. "
                "Pass replace=True if this is an intentional handler swap."
            )
        if capability in self._tools:
            logger.warning("Replacing existing handler for capability '%s'", capability)
        self._tools[capability] = handler

    def get(self, capability: str) -> Callable[[dict[str, Any]], Any]:
        """Get the handler for a capability. Raises ToolNotFoundError if not found."""
        if capability not in self._tools:
            raise ToolNotFoundError(f"No handler registered for capability: {capability}")
        return self._tools[capability]

    def call(self, capability: str, params: dict[str, Any]) -> Any:
        """Call a registered handler with params."""
        handler = self.get(capability)
        return handler(params)

    def list_capabilities(self) -> list[str]:
        """List all registered capability names."""
        return list(self._tools.keys())

    def unregister(self, capability: str) -> None:
        """Remove a registered handler."""
        self._tools.pop(capability, None)
