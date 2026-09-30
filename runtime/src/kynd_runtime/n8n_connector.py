"""n8n webhook connector — receive webhook calls from n8n and route through Kynd.

Runs a minimal HTTP server that accepts POST requests from n8n and dispatches
them through the Kynd executor (gate → broker → tool → audit).

SECURITY
--------
This server fronts capabilities that move money and send messages. It therefore
requires a shared-secret token and binds to loopback by default.

    export KYND_WEBHOOK_TOKEN="$(python -m secrets token_urlsafe 32)"
    server = KyndWebhookServer(executor)   # 127.0.0.1:5000

Callers must send it as ``Authorization: Bearer <token>`` or ``X-Kynd-Token``.
Binding to a non-loopback address is refused unless you pass
``allow_public_bind=True``, and even then a token is mandatory. There is no way
to run this without authentication.

Usage:
    from kynd_runtime.n8n_connector import KyndWebhookServer

    server = KyndWebhookServer(executor, token="...")
    server.start()

n8n webhook URL: http://127.0.0.1:5000/webhook/<capability>

Payload:
    {
        "params": {"target": "user@example.com", "subject": "Hello"},
        "action_type": "send",                 # optional, for block_action_type rules
        "idempotency_key": "n8n-run-1234"      # optional, recommended
    }
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from .executor import Executor, KyndExecutionError
from .tool_registry import ToolNotFoundError

logger = logging.getLogger(__name__)

# Reject oversized bodies before reading them into memory.
MAX_BODY_BYTES = 1_048_576  # 1 MiB
TOKEN_ENV_VAR = "KYND_WEBHOOK_TOKEN"  # noqa: S105 -- this is a var *name*, not a secret value


class WebhookConfigError(Exception):
    """Raised when the webhook server is configured unsafely."""


class KyndWebhookHandler(BaseHTTPRequestHandler):
    """Handle incoming webhook requests from n8n."""

    server_version = "KyndWebhook"
    sys_version = ""  # do not advertise the Python version

    def __init__(self, executor: Executor, token: str, *args: Any, **kwargs: Any) -> None:
        self.executor = executor
        self._token = token
        super().__init__(*args, **kwargs)

    # -- request handling --------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        if not self._authenticate():
            return

        capability = self._parse_capability()
        if capability is None:
            return

        payload = self._read_json_body()
        if payload is None:
            return

        params = payload.get("params", {})
        if not isinstance(params, dict):
            self._send_error(400, "'params' must be an object")
            return

        action_type = payload.get("action_type")
        if action_type is not None and not isinstance(action_type, str):
            self._send_error(400, "'action_type' must be a string")
            return

        idem_key = payload.get("idempotency_key")
        if idem_key is not None:
            if not isinstance(idem_key, str):
                self._send_error(400, "'idempotency_key' must be a string")
                return
            params = {**params, "idempotency_key": idem_key}

        try:
            result = self.executor.execute(capability, params, action_type=action_type)
        except KyndExecutionError as e:
            # Governance denial. The reason is derived from the operator's own
            # constitution, so returning it is intended and useful.
            self._send_json(403, {"status": "denied", "capability": capability, "reason": str(e)})
            return
        except ToolNotFoundError:
            self._send_error(404, f"No handler registered for capability '{capability}'")
            return
        except Exception:
            # Internal failure. Log the detail server-side; return an opaque
            # message so exception text (which can carry connection strings or
            # credentials) never reaches the caller.
            logger.exception("Webhook execution failed for capability=%s", capability)
            self._send_error(500, "Internal error executing capability")
            return

        self._send_json(
            200,
            {
                "status": "ok",
                "capability": capability,
                "result": _json_safe(result),
            },
        )

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        """Unauthenticated liveness probe. Reveals nothing about configuration."""
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        self._send_error(404, "Not found")

    # -- helpers -----------------------------------------------------------

    def _authenticate(self) -> bool:
        supplied = self.headers.get("X-Kynd-Token", "")
        auth = self.headers.get("Authorization", "")
        if not supplied and auth.startswith("Bearer "):
            supplied = auth[len("Bearer ") :]
        # Constant-time compare: a naive == leaks the token via timing.
        if not supplied or not hmac.compare_digest(supplied, self._token):
            logger.warning("Rejected unauthenticated webhook from %s", self.address_string())
            self._send_error(401, "Missing or invalid token")
            return False
        return True

    def _parse_capability(self) -> str | None:
        path_parts = self.path.split("?", 1)[0].strip("/").split("/")
        if len(path_parts) != 2 or path_parts[0] != "webhook" or not path_parts[1]:
            self._send_error(404, "Not found. Use /webhook/<capability>")
            return None
        return path_parts[1]

    def _read_json_body(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send_error(400, "Invalid Content-Length")
            return None
        if content_length < 0:
            self._send_error(400, "Invalid Content-Length")
            return None
        if content_length > MAX_BODY_BYTES:
            # Discard the body in chunks so the client can finish writing and
            # actually read our 413. Never buffered, so an oversized upload
            # still costs no memory. Refusing to drain makes the peer see a
            # connection reset instead of the error we are trying to report.
            self._drain(content_length)
            self._send_error(413, f"Body exceeds {MAX_BODY_BYTES} bytes")
            return None

        body = self.rfile.read(content_length) if content_length else b""
        if not body:
            return {}
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_error(400, "Invalid JSON body")
            return None
        if not isinstance(payload, dict):
            self._send_error(400, "Body must be a JSON object")
            return None
        return payload

    def _drain(self, remaining: int, chunk: int = 65_536, cap: int = 64 * 1024 * 1024) -> None:
        """Read and discard up to ``cap`` bytes of an unwanted request body.

        Bounded so a malicious sender cannot hold the worker open indefinitely
        by declaring an enormous Content-Length.
        """
        remaining = min(remaining, cap)
        while remaining > 0:
            block = self.rfile.read(min(chunk, remaining))
            if not block:
                break
            remaining -= len(block)

    def _send_json(self, status: int, data: dict[str, Any]) -> None:
        try:
            encoded = json.dumps(data).encode()
        except (TypeError, ValueError):
            logger.exception("Response was not JSON serialisable")
            status, encoded = 500, b'{"status": "error", "message": "Unserialisable result"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json(status, {"status": "error", "message": message})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        logger.info("%s - %s", self.address_string(), format % args)


class KyndWebhookServer:
    """HTTP server that routes n8n webhooks through the Kynd executor.

    Authentication is mandatory. The token is taken from the ``token``
    argument or the ``KYND_WEBHOOK_TOKEN`` environment variable.
    """

    def __init__(
        self,
        executor: Executor,
        host: str = "127.0.0.1",
        port: int = 5000,
        token: str | None = None,
        allow_public_bind: bool = False,
    ) -> None:
        self.executor = executor
        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

        resolved = token or os.environ.get(TOKEN_ENV_VAR)
        if not resolved:
            raise WebhookConfigError(
                "A webhook token is required. Pass token=... or set "
                f"{TOKEN_ENV_VAR}. This server fronts capabilities that can "
                "move money; it will not run unauthenticated."
            )
        if len(resolved) < 16:
            raise WebhookConfigError(
                "Webhook token must be at least 16 characters. Generate one with: "
                "python -m secrets token_urlsafe 32"
            )
        self._token = resolved

        if not self._is_loopback(host) and not allow_public_bind:
            raise WebhookConfigError(
                f"Refusing to bind {host!r}, which is reachable off-host. Bind "
                "127.0.0.1 and put a reverse proxy with TLS in front, or pass "
                "allow_public_bind=True if you have accepted that risk."
            )

    @staticmethod
    def _is_loopback(host: str) -> bool:
        if host in ("localhost", ""):
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False

    def _build_server(self) -> ThreadingHTTPServer:
        executor, token = self.executor, self._token

        def handler_factory(*args: Any, **kwargs: Any) -> KyndWebhookHandler:
            return KyndWebhookHandler(executor, token, *args, **kwargs)

        server = ThreadingHTTPServer((self.host, self.port), handler_factory)
        server.daemon_threads = True
        return server

    def start(self) -> None:
        """Start the webhook server and block until stopped."""
        self._server = self._build_server()
        self.port = self._server.server_address[1]
        logger.info("Kynd webhook server listening on %s:%d", self.host, self.port)
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Server stopped")
        finally:
            self._server.server_close()
            self._server = None

    def start_background(self) -> None:
        """Start the server in a daemon thread. Returns once it is listening."""
        if self._server is not None:
            raise RuntimeError("Server already running")
        self._server = self._build_server()
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="kynd-webhook", daemon=True
        )
        self._thread.start()
        logger.info("Kynd webhook server listening on %s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the webhook server and release the socket."""
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None


def _json_safe(value: Any) -> Any:
    """Return value if it is JSON serialisable, else its string form."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
