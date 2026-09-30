"""Langfuse integration — optional tracing wrapper for Kynd executor.

If langfuse is installed, wrap executor.execute() with @observe() for tracing.
If not installed, tracing is a no-op and execution proceeds normally.

Usage:
    from kynd_runtime import Constitution, Executor, ToolRegistry
    from kynd_runtime.observability import with_langfuse
    
    executor = Executor(constitution, registry)
    traced_executor = with_langfuse(executor)
    result = traced_executor.execute("send_email", {"target": "user@example.com"})
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def with_langfuse(executor: Any) -> Any:
    """Wrap an executor with Langfuse tracing if available.
    
    Returns the original executor if langfuse is not installed.
    """
    try:
        from langfuse import observe
    except ImportError:
        logger.info("langfuse not installed — tracing disabled")
        return executor

    class TracedExecutor:
        """Executor wrapper that traces every call with Langfuse."""

        def __init__(self, wrapped_executor: Any) -> None:
            self._wrapped = wrapped_executor

        @observe(as_type="tool")  # type: ignore[untyped-decorator]  # langfuse has
        # no type stubs and is an optional runtime import (see try/except
        # ImportError above); its decorator is untyped so mypy cannot verify
        # what it does to `execute`'s signature. Isolated to this one line —
        # the method body and every other line in this module stay checked.
        def execute(
            self, capability: str, params: dict[str, Any], action_type: str | None = None
        ) -> Any:
            """Trace execution through gate → broker → tool."""
            return self._wrapped.execute(capability, params, action_type=action_type)

        # Logs are properties on the wrapped executor and must be read live.
        # Binding them in __init__ would shadow __getattr__ with a snapshot
        # taken at wrap time, permanently stale.
        @property
        def execution_log(self) -> Any:
            return self._wrapped.execution_log

        @property
        def audit_log(self) -> Any:
            return self._wrapped.audit_log

        def __getattr__(self, name: str) -> Any:
            """Proxy all other attributes to the wrapped executor."""
            return getattr(self._wrapped, name)

    return TracedExecutor(executor)


def configure_langfuse(
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
) -> bool:
    """Configure Langfuse client. Returns True if successful."""
    try:
        import os
        from langfuse import Langfuse

        if public_key:
            os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
        if secret_key:
            os.environ["LANGFUSE_SECRET_KEY"] = secret_key
        if host:
            os.environ["LANGFUSE_HOST"] = host

        # Test the connection. NOTE: this only proves construction succeeds
        # (bad host/malformed key raise here); it does not verify auth against
        # the Langfuse API — the SDK's auth-check method name is UNVERIFIED
        # since langfuse is not installed in this environment and guessing at
        # its API would be worse than the honest, narrower check.
        Langfuse()
        return True
    except ImportError:
        logger.warning("langfuse not installed — configuration skipped")
        return False
    except Exception as e:
        logger.warning("Langfuse configuration failed: %s", e)
        return False
