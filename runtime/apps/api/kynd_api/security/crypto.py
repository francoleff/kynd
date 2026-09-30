"""Credential encryption at rest.

AES-256-GCM via `cryptography`. No invented cryptography anywhere in this
module — every primitive is a call into a reviewed library, and the only
design decisions made here are about key handling and format.

Why GCM: it is authenticated. A ciphertext that has been tampered with fails
to decrypt rather than silently yielding altered plaintext, which for a
credential means an attacker with database write access cannot swap a
customer's Slack token for one pointing at their own workspace.

Key handling:
    Keys come from the environment as `KYND_CREDENTIAL_KEYS`, a comma-separated
    list of `<key_id>:<base64-32-bytes>` entries. The FIRST is the active key
    used for new writes; the rest are kept only to decrypt existing rows. That
    is what makes rotation possible without a flag day: add a new key at the
    front, and old ciphertext keeps working while new writes use the new key.

Each row stores the `key_id` that encrypted it, so decryption never has to
guess.
"""

from __future__ import annotations

import base64
import os
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_ENV_VAR = "KYND_CREDENTIAL_KEYS"  # noqa: S105 - a variable NAME, not a secret

# AES-256 key length, and the 96-bit nonce GCM is specified for. 96 bits is not
# an arbitrary choice: it is the only nonce size for which GCM's security proof
# holds without an extra derivation step.
KEY_BYTES = 32
NONCE_BYTES = 12


class CredentialCryptoError(Exception):
    """Raised when encryption or decryption cannot be performed safely."""


@dataclass(frozen=True)
class EncryptedCredential:
    """A credential ready to be persisted."""

    ciphertext: bytes
    key_id: str
    hint: str


def generate_key() -> str:
    """Generate a new `<key_id>:<base64 key>` entry for the environment."""
    key_id = f"k{secrets.token_hex(4)}"
    key = base64.b64encode(os.urandom(KEY_BYTES)).decode()
    return f"{key_id}:{key}"


def _load_keys() -> list[tuple[str, bytes]]:
    """Parse the configured keys. First entry is the active one.

    Fails closed and loudly: a missing or malformed key is a startup-level
    configuration error, never a reason to fall back to storing plaintext.
    """
    raw = os.environ.get(KEY_ENV_VAR, "").strip()
    if not raw:
        raise CredentialCryptoError(
            f"{KEY_ENV_VAR} is not set. Credentials cannot be stored without an "
            f"encryption key. Generate one with: python -c "
            f"'from kynd_api.security.crypto import generate_key; print(generate_key())'"
        )

    keys: list[tuple[str, bytes]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise CredentialCryptoError(
                f"Malformed {KEY_ENV_VAR} entry: expected '<key_id>:<base64 key>'"
            )
        key_id, encoded = entry.split(":", 1)
        try:
            key = base64.b64decode(encoded)
        except Exception as exc:
            raise CredentialCryptoError(
                f"Key {key_id!r} is not valid base64"
            ) from exc
        if len(key) != KEY_BYTES:
            raise CredentialCryptoError(
                f"Key {key_id!r} is {len(key)} bytes; AES-256 requires {KEY_BYTES}"
            )
        keys.append((key_id.strip(), key))

    if not keys:
        raise CredentialCryptoError(f"{KEY_ENV_VAR} contained no usable keys")
    return keys


def mask(secret: str) -> str:
    """A recognisable but non-recoverable fragment, e.g. 'xoxb-...4f2a'.

    This is the ONLY representation of a credential the frontend ever receives.
    It shows enough for a human to tell which token is installed and not enough
    to use or reconstruct it.
    """
    if not secret:
        return ""
    if len(secret) <= 8:
        # Too short to reveal any of safely.
        return "*" * len(secret)
    prefix = secret[:5] if "-" in secret[:6] else secret[:3]
    return f"{prefix}...{secret[-4:]}"


def encrypt_credential(plaintext: str) -> EncryptedCredential:
    """Encrypt a credential with the active key.

    The nonce is prepended to the ciphertext. A fresh random nonce per
    encryption is mandatory for GCM — reusing one with the same key is a
    catastrophic, key-recovering failure, so it is generated here and never
    derived from anything caller-supplied.
    """
    if not isinstance(plaintext, str) or not plaintext:
        raise CredentialCryptoError("Refusing to encrypt an empty credential")

    key_id, key = _load_keys()[0]
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)

    return EncryptedCredential(
        ciphertext=nonce + ciphertext,
        key_id=key_id,
        hint=mask(plaintext),
    )


def decrypt_credential(blob: bytes, key_id: str) -> str:
    """Decrypt a stored credential. Raises if it cannot be authenticated."""
    if not blob or len(blob) <= NONCE_BYTES:
        raise CredentialCryptoError("Stored credential is missing or truncated")

    keys = dict(_load_keys())
    key = keys.get(key_id)
    if key is None:
        raise CredentialCryptoError(
            f"No key with id {key_id!r} is configured. The credential cannot be "
            f"decrypted — if a key was rotated out, restore it to "
            f"{KEY_ENV_VAR} or have the customer reconnect the integration."
        )

    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")
    except InvalidTag as exc:
        # Authentication failed: the ciphertext was altered, or the wrong key
        # was used. Never fall back to another key — that would turn a
        # tampering signal into a silent success.
        raise CredentialCryptoError(
            "Stored credential failed authentication. It may have been tampered "
            "with, or was encrypted with a different key."
        ) from exc
