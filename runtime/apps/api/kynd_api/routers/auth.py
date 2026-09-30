"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..db import get_db
from ..deps import (
    AuthContext,
    WorkspaceContext,
    get_auth,
    get_client_ip,
    get_optional_auth,
)
from ..models import Membership, Role, Workspace
from ..schemas import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    MessageResponse,
    SignupRequest,
    UserOut,
    WorkspaceOut,
    WorkspaceSummary,
)
from ..security import sessions
from ..security.passwords import PasswordPolicyError
from ..security.permissions import permissions_for_role
from ..security.ratelimit import RateLimiter, client_key
from ..services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_settings = get_settings()
_login_limiter = RateLimiter(*_settings.rate_limit_login)
_signup_limiter = RateLimiter(*_settings.rate_limit_signup)


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        max_age=settings.session_idle_seconds,
        httponly=True,  # unreadable from JavaScript: XSS cannot steal it
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.cookie_name,
        domain=settings.cookie_domain,
        path="/",
    )


def _enforce_limit(limiter: RateLimiter, key: str) -> None:
    allowed, retry_after = limiter.check(key)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again shortly.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> AuthResponse:
    """Create an account, its first workspace, and an OWNER membership."""
    ip = get_client_ip(request)
    _enforce_limit(_signup_limiter, client_key(ip))

    try:
        user, workspace, membership = auth_service.signup(
            db,
            email=payload.email,
            password=payload.password,
            workspace_name=payload.workspace_name,
            name=payload.name,
        )
    except auth_service.EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    _, token = sessions.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    db.commit()

    _set_session_cookie(response, token)
    return AuthResponse(
        user=UserOut.from_model(user),
        workspace=WorkspaceOut.from_model(workspace),
        role=membership.role,
    )


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> AuthResponse:
    ip = get_client_ip(request)
    key = client_key(ip, payload.email)
    _enforce_limit(_login_limiter, key)

    try:
        user = auth_service.authenticate(db, payload.email, payload.password)
    except auth_service.InvalidCredentials as exc:
        db.commit()  # persist nothing sensitive; keeps the session clean
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    # A legitimate user who mistyped a few times should not stay throttled.
    _login_limiter.reset(key)

    pairs = auth_service.workspaces_for_user(db, user.id)
    if not pairs:
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not belong to any workspace",
        )
    workspace, role = pairs[0]

    _, token = sessions.create_session(
        db,
        user,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip,
    )
    db.commit()

    _set_session_cookie(response, token)
    return AuthResponse(
        user=UserOut.from_model(user),
        workspace=WorkspaceOut.from_model(workspace),
        role=role,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    response: Response,
    auth: AuthContext | None = Depends(get_optional_auth),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    """Revoke the current session server-side and clear the cookie.

    Idempotent: logging out when already logged out is a success, not an error.
    """
    if auth is not None:
        sessions.revoke_session(db, auth.session)
        db.commit()
    _clear_session_cookie(response)
    return MessageResponse(message="Signed out")


@router.get("/me", response_model=MeResponse)
def me(
    auth: AuthContext = Depends(get_auth),
    db: DbSession = Depends(get_db),
    x_kynd_workspace: str | None = None,
) -> MeResponse:
    """The current user, their workspaces, and their permissions in the active one.

    The frontend renders from `permissions`, so the UI and the API agree on
    authority by construction — a button is hidden for exactly the reason the
    endpoint behind it would 403.
    """
    pairs = auth_service.workspaces_for_user(db, auth.user.id)
    summaries = [
        WorkspaceSummary(id=ws.id, name=ws.name, slug=ws.slug, role=role)
        for ws, role in pairs
    ]

    current: Workspace | None = None
    current_role: Role | None = None
    if x_kynd_workspace:
        for ws, role in pairs:
            if ws.id == x_kynd_workspace:
                current, current_role = ws, role
                break
    elif pairs:
        current, current_role = pairs[0]

    db.commit()  # persist the session's slid expiry

    return MeResponse(
        user=UserOut.from_model(auth.user),
        workspaces=summaries,
        current_workspace=WorkspaceOut.from_model(current) if current else None,
        role=current_role,
        permissions=(
            sorted(p.value for p in permissions_for_role(current_role))
            if current_role
            else []
        ),
    )


@router.post("/logout-all", response_model=MessageResponse)
def logout_all(
    response: Response,
    auth: AuthContext = Depends(get_auth),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    """Revoke every session for this user — the 'I think I was compromised' button."""
    count = sessions.revoke_all_sessions_for_user(db, auth.user.id)
    db.commit()
    _clear_session_cookie(response)
    return MessageResponse(message=f"Signed out of {count} session(s)")
