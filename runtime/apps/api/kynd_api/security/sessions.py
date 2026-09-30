"""Session issuance, verification, and revocation.

Model: opaque random token in an httpOnly cookie; only its SHA-256 is stored.
This mirrors the pattern the runtime already uses for approval tokens
(`secrets.token_urlsafe(32)` + server-side lookup) rather than inventing a
second scheme.

Why not JWT: a JWT cannot be revoked before its expiry without a server-side
denylist — at which point it is a session table with extra cryptography and a
larger cookie. Logout must be real, so the session is real.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..config import get_settings
from ..models import SessionToken, User, utcnow

TOKEN_BYTES = 32  # 256 bits


def generate_token() -> str:
    """A new, unguessable session token. Returned to the client exactly once."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 of the token, hex.

    A plain fast hash is correct here, unlike for passwords: the input is 256
    bits of CSPRNG output, so there is no dictionary to attack and no benefit
    from a slow KDF — only a per-request cost on every authenticated call.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    db: DbSession,
    user: User,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[SessionToken, str]:
    """Issue a session. Returns (row, plaintext_token).

    The plaintext is never persisted and is never returned again after this
    call — exactly like the runtime's `issue_approval`.
    """
    settings = get_settings()
    now = utcnow()
    token = generate_token()

    session_row = SessionToken(
        user_id=user.id,
        token_hash=hash_token(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.session_idle_seconds),
        absolute_expires_at=now + timedelta(seconds=settings.session_absolute_seconds),
        user_agent=(user_agent or "")[:400] or None,
        ip_address=(ip_address or "")[:64] or None,
    )
    db.add(session_row)
    db.flush()
    return session_row, token


def resolve_session(db: DbSession, token: str | None) -> SessionToken | None:
    """Look up a live session by its plaintext token, or None.

    Also slides the idle expiry forward on each use, bounded by the session's
    absolute expiry — an active user is not logged out mid-work, but a stolen
    cookie still dies at the absolute ceiling.
    """
    if not token:
        return None

    token_hash = hash_token(token)
    row = db.execute(
        select(SessionToken).where(SessionToken.token_hash == token_hash)
    ).scalar_one_or_none()

    if row is None:
        return None

    # Constant-time compare on the hash. The lookup above is already an exact
    # index match so this is belt-and-braces, but it costs nothing and removes
    # any argument about comparison timing.
    if not hmac.compare_digest(row.token_hash, token_hash):
        return None

    now = utcnow()
    if not row.is_valid(now):
        return None

    settings = get_settings()
    new_expiry = min(
        now + timedelta(seconds=settings.session_idle_seconds),
        row.absolute_expires_at,
    )
    row.last_seen_at = now
    row.expires_at = new_expiry
    return row


def revoke_session(db: DbSession, session_row: SessionToken) -> None:
    """Revoke one session. Idempotent."""
    if session_row.revoked_at is None:
        session_row.revoked_at = utcnow()


def revoke_all_sessions_for_user(db: DbSession, user_id: str) -> int:
    """Revoke every live session for a user. Returns how many were revoked.

    Used on password change and by an operator responding to a compromise.
    """
    now = utcnow()
    rows = (
        db.execute(
            select(SessionToken).where(
                SessionToken.user_id == user_id,
                SessionToken.revoked_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.revoked_at = now
    return len(rows)


def purge_expired_sessions(db: DbSession) -> int:
    """Delete rows that can never authenticate again. Returns the count.

    Housekeeping only — `resolve_session` never trusts an expired row, so this
    is about table size, not correctness.
    """
    now = utcnow()
    rows = (
        db.execute(
            select(SessionToken).where(SessionToken.absolute_expires_at <= now)
        )
        .scalars()
        .all()
    )
    for row in rows:
        db.delete(row)
    return len(rows)
