"""Authentication and account provisioning.

Orchestration only. It owns no governance decision — it creates identity and
tenancy rows so that later phases have something to scope against.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ..models import Membership, Role, User, Workspace
from ..schemas import slugify
from ..security import passwords


class AuthError(Exception):
    """A recoverable, customer-facing authentication problem."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def unique_workspace_slug(db: DbSession, name: str) -> str:
    """A slug that does not collide.

    Appends -2, -3, ... on collision. The uniqueness is also enforced by a DB
    constraint, so a race here surfaces as an IntegrityError rather than two
    workspaces sharing a slug.
    """
    base = slugify(name)
    candidate = base
    suffix = 2
    while db.execute(
        select(func.count()).select_from(Workspace).where(Workspace.slug == candidate)
    ).scalar_one():
        candidate = f"{base}-{suffix}"[:60]
        suffix += 1
    return candidate


def signup(
    db: DbSession,
    email: str,
    password: str,
    workspace_name: str,
    name: str | None = None,
) -> tuple[User, Workspace, Membership]:
    """Create a user, their first workspace, and an OWNER membership.

    All three or none. A user with no workspace cannot use the product, and a
    workspace with no owner cannot be administered — a partial signup would
    produce an account that is broken in a way the customer cannot fix
    themselves.

    The caller commits. This function only flushes, so it composes inside a
    larger transaction.
    """
    normalized = normalize_email(email)

    existing = db.execute(
        select(User).where(User.email_normalized == normalized)
    ).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegistered("An account with this email already exists")

    # Raises PasswordPolicyError (a ValueError) before anything is written.
    password_hash = passwords.hash_password(password)

    user = User(
        email=email.strip(),
        email_normalized=normalized,
        password_hash=password_hash,
        name=name or None,
    )
    db.add(user)

    workspace = Workspace(
        name=workspace_name.strip(),
        slug=unique_workspace_slug(db, workspace_name),
    )
    db.add(workspace)
    db.flush()  # assign ids

    membership = Membership(
        user_id=user.id,
        workspace_id=workspace.id,
        role=Role.OWNER,
    )
    db.add(membership)

    try:
        db.flush()
    except IntegrityError as exc:
        # Two simultaneous signups with the same email: the unique index is the
        # real arbiter, and the loser gets the same error as if it had checked
        # first. Without this the second request would surface a 500.
        db.rollback()
        raise EmailAlreadyRegistered("An account with this email already exists") from exc

    return user, workspace, membership


def authenticate(db: DbSession, email: str, password: str) -> User:
    """Verify credentials. Raises InvalidCredentials for every failure.

    One error for "no such user" and "wrong password", and a real argon2
    verification is performed even when the user does not exist — otherwise
    both the message and the response time reveal which emails have accounts.
    """
    normalized = normalize_email(email)
    user = db.execute(
        select(User).where(User.email_normalized == normalized)
    ).scalar_one_or_none()

    if user is None:
        passwords.waste_time_like_a_real_verification()
        raise InvalidCredentials("Invalid email or password")

    if not passwords.verify_password(user.password_hash, password):
        raise InvalidCredentials("Invalid email or password")

    if not user.is_active:
        raise InvalidCredentials("Invalid email or password")

    # Transparently upgrade a hash made with older cost parameters.
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)

    return user


def workspaces_for_user(db: DbSession, user_id: str) -> list[tuple[Workspace, Role]]:
    rows = db.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user_id)
        .order_by(Membership.created_at.asc())
    ).all()
    return [(workspace, role) for workspace, role in rows]
