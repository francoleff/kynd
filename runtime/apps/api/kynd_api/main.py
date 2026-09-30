"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routers import approvals, audit, auth, executions, governance, proposals, slack, slack_webhooks, workspace

logger = logging.getLogger("kynd_api")

API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.assert_production_safety()
    logger.info("kynd api starting environment=%s", settings.environment)
    yield
    logger.info("kynd api stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kynd OS API",
        version=API_VERSION,
        description=(
            "Deterministic governance for AI and automation actions. "
            "The API orchestrates; the Kynd Runtime enforces."
        ),
        lifespan=lifespan,
        # Interactive docs are useful in development and an unnecessary
        # information disclosure in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        # Required for the session cookie to be sent cross-origin (web on :3000,
        # api on :8000). This is exactly why allow_origins must never be "*" —
        # the two settings together would let any site make authenticated calls.
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Kynd-Workspace"],
    )

    @app.middleware("http")
    async def correlation_and_timing(request: Request, call_next):
        """Attach a request id and log the timing of every request.

        The id is returned in `X-Request-ID` and is what a customer quotes in a
        support ticket — it is how an opaque customer-facing error maps back to
        a specific server-side log line (mission sections 27 and 49).
        """
        request_id = secrets.token_hex(8)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = (time.perf_counter() - started) * 1000
            logger.exception(
                "request_failed id=%s method=%s path=%s ms=%.1f",
                request_id,
                request.method,
                request.url.path,
                elapsed,
            )
            raise
        elapsed = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request id=%s method=%s path=%s status=%d ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed,
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        """Never leak a stack trace to a customer.

        The detail stays in the server log, correlated by request id; the
        client gets an id it can quote. Mission section 32.
        """
        request_id = getattr(request.state, "request_id", None) or secrets.token_hex(8)
        logger.exception("unhandled id=%s path=%s", request_id, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Something went wrong on our side.",
                "error_id": request_id,
            },
            headers={"X-Request-ID": request_id},
        )

    @app.get("/health", tags=["system"])
    def health() -> dict:
        """Liveness probe. Reveals nothing about configuration."""
        return {"status": "ok", "version": API_VERSION}

    @app.get("/health/ready", tags=["system"])
    def readiness() -> JSONResponse:
        """Readiness: can we actually reach the database?

        A liveness check that returns ok while the DB is unreachable is how a
        broken deploy passes its health check and takes traffic.
        """
        from sqlalchemy import text

        from .db import engine

        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            logger.exception("readiness check failed")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"status": "unavailable", "database": "unreachable"},
            )
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "database": "ok", "version": API_VERSION},
        )

    app.include_router(auth.router)
    app.include_router(workspace.router)
    app.include_router(governance.router)
    app.include_router(approvals.router)
    app.include_router(executions.router)
    app.include_router(audit.router)
    app.include_router(slack.router)
    app.include_router(slack_webhooks.router)
    app.include_router(proposals.router)
    return app


app = create_app()
