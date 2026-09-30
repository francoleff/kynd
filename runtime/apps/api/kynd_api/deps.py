"""Request dependencies: identity, tenancy, authorization.

This module is the security spine of the API. Three rules it exists to enforce:

1. The authenticated user comes from the session cookie, never from a body.
2. The workspace comes from that user's MEMBERSHIP, never from a client value.
3. Authorization is a permission lookup, never an inline role comparison.

`get_workspace_context` is the ONLY place in the codebase that resolves a
workspace id for a request. If a second one ever appears, that is the bug.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from .config import get_settings
from .db import get_db
from .models import Membership, Role, SessionToken, User, Workspace
from .security.permissions import Permission, role_has_permission
from .security.sessions import resolve_session


@dataclass(frozen=True)
class AuthContext:
    """An authenticated user and the live session that proved it."""

    user: User
    session: SessionToken


@dataclass(frozen=True)
class WorkspaceContext:
    """A user acting inside one workspace, with a server-resolved role.

    Every tenant-scoped query in the application takes its workspace_id from
    THIS object. Not from a path parameter, not from a header, not from a body
    field — from a membership row the server looked up itself.
    """

    user: User
    session: SessionToken
    workspace: Workspace
    membership: Membership

    @property
    def workspace_id(self) -> str:
        return self.workspace.id

    @property
    def role(self) -> Role:
        return self.membership.role

    def can(self, permission: Permission) -> bool:
        return role_has_permission(self.role, permission)


def get_client_ip(request: Request) -> str | None:
    """Best-effort client IP.

    NOTE, deliberately: X-Forwarded-For is trusted ONLY because the production
    deployment terminates at a proxy that overwrites it. A directly-exposed
    API must not trust this header — an attacker sets it freely and defeats
    per-IP rate limiting. This constraint is recorded in the deployment doc.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client is not None:
        return request.client.host[:64]
    return None


def get_optional_auth(
    request: Request,
    db: DbSession = Depends(get_db),
) -> AuthContext | None:
    """Resolve the session cookie into a user, or None. Never raises."""
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    session_row = resolve_session(db, token)
    if session_row is None:
        return None

    user = db.get(User, session_row.user_id)
    if user is None or not user.is_active:
        return None

    return AuthContext(user=user, session=session_row)


def get_auth(
    auth: AuthContext | None = Depends(get_optional_auth),
) -> AuthContext:
    """Require an authenticated user, else 401."""
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return auth


def get_workspace_context(
    auth: AuthContext = Depends(get_auth),
    db: DbSession = Depends(get_db),
    x_kynd_workspace: str | None = Header(default=None),
) -> WorkspaceContext:
    """Resolve the workspace this request acts in. THE tenancy boundary.

    `X-Kynd-Workspace` is a *selector*, not an authority: a user with several
    workspaces uses it to say which one they mean. It is always validated
    against a real membership row for the authenticated user, so supplying
    another tenant's id yields 404 — the same response as an id that does not
    exist, so the header cannot be used to probe for valid workspace ids.

    With no header, the user's single membership is used; if they have several
    and named none, that is a 400 rather than a silent guess.
    """
    memberships = (
        db.execute(
            select(Membership)
            .where(Membership.user_id == auth.user.id)
            .order_by(Membership.created_at.asc())
        )
        .scalars()
        .all()
    )

    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not belong to any workspace",
        )

    if x_kynd_workspace:
        membership = next(
            (m for m in memberships if m.workspace_id == x_kynd_workspace), None
        )
        if membership is None:
            # Deliberately 404, not 403. A 403 would confirm the workspace
            # exists and belongs to someone else — a free enumeration oracle.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )
    elif len(memberships) == 1:
        membership = memberships[0]
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Multiple workspaces available; specify one with the "
                "X-Kynd-Workspace header"
            ),
        )

    workspace = db.get(Workspace, membership.workspace_id)
    if workspace is None:
        # Referential integrity says this cannot happen; fail closed anyway.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    return WorkspaceContext(
        user=auth.user,
        session=auth.session,
        workspace=workspace,
        membership=membership,
    )


def require_permission(permission: Permission):
    """Dependency factory: 403 unless the caller's role holds `permission`.

    Usage:

        @router.post("/integrations")
        def connect(
            ctx: WorkspaceContext = Depends(
                require_permission(Permission.INTEGRATION_CONNECT)
            ),
        ):
            ...

    Returns the same WorkspaceContext, so a route gets identity, tenancy, and
    authorization from a single dependency and cannot accidentally take the
    context without the check.
    """

    def _dependency(
        ctx: WorkspaceContext = Depends(get_workspace_context),
    ) -> WorkspaceContext:
        if not ctx.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Your role ({ctx.role.value}) does not permit "
                    f"{permission.value}"
                ),
            )
        return ctx

    return _dependency
