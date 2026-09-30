"""Password hashing.

argon2id via argon2-cffi — the PHC winner and the current OWASP first choice.
No custom cryptography anywhere in this module; every operation is a call into
a reviewed library.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError, VerificationError

# OWASP Password Storage Cheat Sheet (argon2id): m=19456 KiB, t=2, p=1 is the
# recommended minimum. Using it rather than a hand-tuned guess.
_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

# Long enough to resist offline cracking, short enough to be usable. The upper
# bound exists because argon2's cost is linear in input length past the block
# size — an unbounded password field is a cheap denial-of-service.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the minimum policy."""


def validate_password(password: str) -> None:
    """Raise PasswordPolicyError if the password is unacceptable.

    Deliberately minimal: length only. Composition rules ("must contain a
    symbol") measurably push users toward `Password1!` and are advised against
    by both NIST SP 800-63B and OWASP. Length is what actually helps.
    """
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at most {MAX_PASSWORD_LENGTH} characters"
        )


def hash_password(password: str) -> str:
    """Validate policy, then hash. Returns a PHC-format string."""
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time-ish verification. Never raises on a wrong password.

    Returns False for every failure mode — mismatch, corrupt hash, wrong
    algorithm. A caller must not be able to distinguish "no such user" from
    "wrong password" by catching different exceptions.
    """
    if not password_hash or not isinstance(password, str):
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether a stored hash was made with weaker parameters than current policy.

    Lets the cost parameters be raised over time and applied transparently on
    each successful login, instead of leaving early users on 2026 parameters
    forever.
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# A fixed, valid argon2id hash of a random throwaway value. Used to burn the
# same CPU time on a login attempt for a nonexistent email as for a real one —
# otherwise response timing tells an attacker which emails have accounts.
DUMMY_HASH = _hasher.hash("kynd-timing-equalizer-not-a-real-password")


def waste_time_like_a_real_verification() -> None:
    """Spend a verification's worth of CPU on a known-bad comparison."""
    verify_password(DUMMY_HASH, "definitely-not-the-password")
