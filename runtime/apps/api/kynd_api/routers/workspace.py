"""Workspace and membership routes.

Every handler here takes its workspace from `require_permission(...)`, which
resolves tenancy server-side. No handler accepts a workspace id as an
argument.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..deps import WorkspaceContext, require_permission
from ..models import Membership, Role, User, utcnow
from ..schemas import MembershipOut, MessageResponse, WorkspaceOut
from ..security.permissions import Permission

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceOut)
def get_workspace(
    ctx: WorkspaceContext = Depends(require_permission(Permission.WORKSPACE_READ)),
) -> WorkspaceOut:
    return WorkspaceOut.from_model(ctx.workspace)


@router.patch("", response_model=WorkspaceOut)
def update_workspace(
    payload: dict,
    ctx: WorkspaceContext = Depends(require_permission(Permission.WORKSPACE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> WorkspaceOut:
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        ctx.workspace.name = name.strip()[:200]
    db.commit()
    db.refresh(ctx.workspace)
    return WorkspaceOut.from_model(ctx.workspace)


@router.post("/complete-onboarding", response_model=WorkspaceOut)
def complete_onboarding(
    ctx: WorkspaceContext = Depends(require_permission(Permission.WORKSPACE_UPDATE)),
    db: DbSession = Depends(get_db),
) -> WorkspaceOut:
    if ctx.workspace.onboarding_completed_at is None:
        ctx.workspace.onboarding_completed_at = utcnow()
    db.commit()
    db.refresh(ctx.workspace)
    return WorkspaceOut.from_model(ctx.workspace)


@router.get("/members", response_model=list[MembershipOut])
def list_members(
    ctx: WorkspaceContext = Depends(require_permission(Permission.MEMBER_READ)),
    db: DbSession = Depends(get_db),
) -> list[MembershipOut]:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        # Tenant scope. Every query touching customer data carries this.
        .where(Membership.workspace_id == ctx.workspace_id)
        .order_by(Membership.created_at.asc())
    ).all()

    return [
        MembershipOut(
            id=membership.id,
            user_id=user.id,
            workspace_id=membership.workspace_id,
            role=membership.role,
            email=user.email,
            name=user.name,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


def _load_member(db: DbSession, ctx: WorkspaceContext, membership_id: str) -> Membership:
    """Load a membership, scoped to the caller's workspace.

    The scope in this WHERE clause is what stops an IDOR: a membership id from
    another tenant simply does not match, and returns 404 rather than 403 so
    the response cannot confirm the id exists elsewhere.
    """
    membership = db.execute(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.workspace_id == ctx.workspace_id,
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    return membership


def _count_owners(db: DbSession, workspace_id: str) -> int:
    return len(
        db.execute(
            select(Membership).where(
                Membership.workspace_id == workspace_id,
                Membership.role == Role.OWNER,
            )
        )
        .scalars()
        .all()
    )


@router.patch("/members/{membership_id}", response_model=MembershipOut)
def update_member_role(
    membership_id: str,
    payload: dict,
    ctx: WorkspaceContext = Depends(require_permission(Permission.MEMBER_UPDATE_ROLE)),
    db: DbSession = Depends(get_db),
) -> MembershipOut:
    membership = _load_member(db, ctx, membership_id)

    raw_role = payload.get("role")
    try:
        new_role = Role(raw_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown role: {raw_role!r}",
        ) from exc

    # Only an OWNER may create another OWNER. An ADMIN who could mint owners
    # could promote themselves and take the workspace.
    if new_role == Role.OWNER and ctx.role != Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an OWNER can grant the OWNER role",
        )

    # A workspace with no owner cannot be administered or cancelled by anyone.
    if (
        membership.role == Role.OWNER
        and new_role != Role.OWNER
        and _count_owners(db, ctx.workspace_id) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace must always have at least one OWNER",
        )

    membership.role = new_role
    db.commit()
    db.refresh(membership)

    user = db.get(User, membership.user_id)
    return MembershipOut(
        id=membership.id,
        user_id=membership.user_id,
        workspace_id=membership.workspace_id,
        role=membership.role,
        email=user.email if user else "",
        name=user.name if user else None,
        created_at=membership.created_at,
    )


@router.delete("/members/{membership_id}", response_model=MessageResponse)
def remove_member(
    membership_id: str,
    ctx: WorkspaceContext = Depends(require_permission(Permission.MEMBER_REMOVE)),
    db: DbSession = Depends(get_db),
) -> MessageResponse:
    membership = _load_member(db, ctx, membership_id)

    if membership.role == Role.OWNER and _count_owners(db, ctx.workspace_id) <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A workspace must always have at least one OWNER",
        )

    db.delete(membership)
    db.commit()
    return MessageResponse(message="Member removed")
