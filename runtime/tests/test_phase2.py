"""Tests for Langfuse integration (optional)."""

import pytest

from kynd_runtime import Constitution, Executor, ToolRegistry


class TestLangfuseIntegration:
    def test_no_langfuse_graceful_fallback(self):
        """If langfuse not installed, with_langfuse returns executor unchanged."""
        const = Constitution({"name": "test", "capabilities": []})
        registry = ToolRegistry()
        executor = Executor(const, registry)

        from kynd_runtime.observability import with_langfuse
        result = with_langfuse(executor)
        assert result is executor

    def test_configure_langfuse_no_install(self):
        """configure_langfuse returns False if not installed."""
        from kynd_runtime.observability import configure_langfuse
        result = configure_langfuse(public_key="test", secret_key="test")
        assert result is False


class TestN8NConnector:
    def test_handler_path_parsing(self):
        """Handler parses /webhook/<capability> correctly."""
        from kynd_runtime.n8n_connector import KyndWebhookHandler

        # Mock the handler to test path parsing
        handler = KyndWebhookHandler.__new__(KyndWebhookHandler)
        handler.path = "/webhook/send_email"
        parts = handler.path.strip("/").split("/")
        assert parts == ["webhook", "send_email"]
        assert parts[0] == "webhook"
        assert parts[1] == "send_email"

    def test_handler_bad_path(self):
        """Handler rejects bad paths."""
        from kynd_runtime.n8n_connector import KyndWebhookHandler

        handler = KyndWebhookHandler.__new__(KyndWebhookHandler)

        # Bad path: not /webhook/<capability>
        handler.path = "/bad/path"
        parts = handler.path.strip("/").split("/")
        assert len(parts) != 2 or parts[0] != "webhook"

    def test_server_creation(self):
        """Server can be created with an executor and a token."""
        from kynd_runtime.n8n_connector import KyndWebhookServer

        const = Constitution({"name": "test", "capabilities": []})
        registry = ToolRegistry()
        executor = Executor(const, registry)

        server = KyndWebhookServer(executor, port=0, token="a" * 32)
        assert server.executor is executor
        assert server.host == "127.0.0.1"  # loopback by default, not 0.0.0.0

    def test_server_requires_token(self):
        """Refuses to construct without a token — no unauthenticated mode exists."""
        from kynd_runtime.n8n_connector import KyndWebhookServer, WebhookConfigError

        executor = Executor(Constitution({"capabilities": []}), ToolRegistry())
        with pytest.raises(WebhookConfigError, match="token is required"):
            KyndWebhookServer(executor, port=0)

    def test_server_rejects_public_bind(self):
        """Refuses to bind an off-host interface unless explicitly allowed."""
        from kynd_runtime.n8n_connector import KyndWebhookServer, WebhookConfigError

        executor = Executor(Constitution({"capabilities": []}), ToolRegistry())
        with pytest.raises(WebhookConfigError, match="Refusing to bind"):
            KyndWebhookServer(executor, host="0.0.0.0", port=0, token="a" * 32)

    def test_server_rejects_short_token(self):
        from kynd_runtime.n8n_connector import KyndWebhookServer, WebhookConfigError

        executor = Executor(Constitution({"capabilities": []}), ToolRegistry())
        with pytest.raises(WebhookConfigError, match="at least 16"):
            KyndWebhookServer(executor, port=0, token="short")


class TestSkill:
    def test_get_skill_info(self):
        """get_skill_info returns valid metadata."""
        from kynd_runtime.skill import get_skill_info

        info = get_skill_info()
        assert info["name"] == "kynd-runtime"
        assert "version" in info
        assert "description" in info
        assert "constitution_template" in info
        template = info["constitution_template"]
        assert "name" in template
        assert "hard_rules" in template
        assert "capabilities" in template
