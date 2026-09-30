"""Credential security tests.

Two things under test, and the second matters more than the first:

1. The cryptography behaves correctly (round trip, tamper detection, rotation).
2. A credential NEVER escapes into anywhere a human or an attacker could read
   it — not the runtime's execution log, not an API response, not a log line.

Point 2 is the one that would actually leak a customer's Slack token, and it
is asserted by scanning REAL output from REAL execution, not by reading code.
"""

from __future__ import annotations

import base64
import json
import logging
import os

import pytest

from kynd_api.security import crypto
from kynd_api.security.crypto import (
    CredentialCryptoError,
    decrypt_credential,
    encrypt_credential,
    generate_key,
    mask,
)

SECRET = "xoxb-1234567890-ABCDEFGHIJKLMNOP-supersecrettokenvalue"


@pytest.fixture(autouse=True)
def _configured_key(monkeypatch):
    monkeypatch.setenv(crypto.KEY_ENV_VAR, generate_key())


class TestEncryption:
    def test_round_trip(self):
        encrypted = encrypt_credential(SECRET)
        assert decrypt_credential(encrypted.ciphertext, encrypted.key_id) == SECRET

    def test_ciphertext_does_not_contain_the_plaintext(self):
        encrypted = encrypt_credential(SECRET)
        assert SECRET.encode() not in encrypted.ciphertext
        assert b"xoxb" not in encrypted.ciphertext

    def test_same_plaintext_encrypts_differently_every_time(self):
        """A fresh nonce per encryption.

        Identical ciphertexts would tell an attacker with database read access
        which workspaces share a credential — and nonce reuse in GCM is a
        key-recovering failure, not a cosmetic one.
        """
        first = encrypt_credential(SECRET)
        second = encrypt_credential(SECRET)
        assert first.ciphertext != second.ciphertext
        assert decrypt_credential(first.ciphertext, first.key_id) == SECRET
        assert decrypt_credential(second.ciphertext, second.key_id) == SECRET

    def test_tampered_ciphertext_is_rejected(self):
        """GCM is authenticated: altered ciphertext must fail, not decrypt."""
        encrypted = encrypt_credential(SECRET)
        tampered = bytearray(encrypted.ciphertext)
        tampered[-1] ^= 0x01

        with pytest.raises(CredentialCryptoError) as exc:
            decrypt_credential(bytes(tampered), encrypted.key_id)
        assert "authentication" in str(exc.value).lower()

    def test_truncated_ciphertext_is_rejected(self):
        encrypted = encrypt_credential(SECRET)
        with pytest.raises(CredentialCryptoError):
            decrypt_credential(encrypted.ciphertext[:8], encrypted.key_id)

    def test_empty_credential_is_refused(self):
        with pytest.raises(CredentialCryptoError):
            encrypt_credential("")

    def test_missing_key_configuration_fails_closed(self, monkeypatch):
        """No key must mean 'refuse', never 'store it in plaintext'."""
        monkeypatch.delenv(crypto.KEY_ENV_VAR, raising=False)
        with pytest.raises(CredentialCryptoError) as exc:
            encrypt_credential(SECRET)
        assert crypto.KEY_ENV_VAR in str(exc.value)

    def test_wrong_key_length_is_rejected(self, monkeypatch):
        short = base64.b64encode(os.urandom(16)).decode()
        monkeypatch.setenv(crypto.KEY_ENV_VAR, f"kbad:{short}")
        with pytest.raises(CredentialCryptoError) as exc:
            encrypt_credential(SECRET)
        assert "AES-256" in str(exc.value)


class TestKeyRotation:
    def test_old_ciphertext_still_decrypts_after_rotation(self, monkeypatch):
        """Rotation must not orphan existing credentials."""
        old_key = generate_key()
        monkeypatch.setenv(crypto.KEY_ENV_VAR, old_key)
        encrypted = encrypt_credential(SECRET)

        # New key goes to the FRONT; the old one is retained for reads.
        new_key = generate_key()
        monkeypatch.setenv(crypto.KEY_ENV_VAR, f"{new_key},{old_key}")

        assert decrypt_credential(encrypted.ciphertext, encrypted.key_id) == SECRET

        # New writes use the new key.
        fresh = encrypt_credential(SECRET)
        assert fresh.key_id == new_key.split(":")[0]

    def test_removing_a_key_gives_an_actionable_error(self, monkeypatch):
        old_key = generate_key()
        monkeypatch.setenv(crypto.KEY_ENV_VAR, old_key)
        encrypted = encrypt_credential(SECRET)

        monkeypatch.setenv(crypto.KEY_ENV_VAR, generate_key())
        with pytest.raises(CredentialCryptoError) as exc:
            decrypt_credential(encrypted.ciphertext, encrypted.key_id)
        # The message must tell an operator what to do, not just that it failed.
        assert "reconnect" in str(exc.value).lower()


    def test_wrong_key_does_not_silently_fall_back_to_another(self, monkeypatch):
        """Tampering must fail, even when a key that CAN decrypt is configured.

        Found by mutation testing: a `for key in keys: try: decrypt` fallback
        loop in the except-branch passed every other test in this file, because
        no test had two valid keys loaded at once while decrypting under the
        wrong key_id. That fallback would turn a tampering signal into a silent
        success and defeat the point of using an authenticated cipher.
        """
        key_a = generate_key()
        key_b = generate_key()
        monkeypatch.setenv(crypto.KEY_ENV_VAR, key_a)
        encrypted = encrypt_credential(SECRET)

        # Both keys configured. Ask for the WRONG one by id.
        monkeypatch.setenv(crypto.KEY_ENV_VAR, f"{key_a},{key_b}")
        wrong_key_id = key_b.split(":")[0]

        with pytest.raises(CredentialCryptoError) as exc:
            decrypt_credential(encrypted.ciphertext, wrong_key_id)
        assert "authentication" in str(exc.value).lower()

    def test_tampering_is_rejected_even_with_many_keys_loaded(self, monkeypatch):
        """The same gap, from the tampering direction."""
        keys = [generate_key() for _ in range(3)]
        monkeypatch.setenv(crypto.KEY_ENV_VAR, ",".join(keys))
        encrypted = encrypt_credential(SECRET)

        tampered = bytearray(encrypted.ciphertext)
        tampered[-1] ^= 0xFF
        with pytest.raises(CredentialCryptoError):
            decrypt_credential(bytes(tampered), encrypted.key_id)


class TestMasking:
    def test_hint_is_recognisable_but_not_recoverable(self):
        hint = mask(SECRET)
        assert hint.endswith(SECRET[-4:])
        assert SECRET not in hint
        assert len(hint) < 20

    def test_short_secrets_are_fully_masked(self):
        assert set(mask("abc123")) == {"*"}

    def test_encrypt_produces_a_safe_hint(self):
        assert encrypt_credential(SECRET).hint == mask(SECRET)


class TestCredentialNeverLeaks:
    """The tests that actually protect a customer's token."""

    def test_credential_never_reaches_the_runtime_execution_log(
        self, client, db, tmp_path, monkeypatch
    ):
        """Audit finding S-1, asserted against REAL runtime storage.

        The handler holds the decrypted credential in its closure and uses it,
        but the credential is never a param — so it must be absent from the
        durable execution log the audit UI reads from.
        """
        from kynd_api.config import get_settings
        from kynd_api.models import (
            Integration,
            IntegrationProvider,
            IntegrationStatus,
            Workspace,
            WorkspaceCapability,
        )
        from kynd_api.runtime.store_factory import get_store
        from kynd_api.services.execution_service import ExecutionOutcome, execute_action

        monkeypatch.setattr(
            get_settings(), "runtime_state_dir", str(tmp_path), raising=False
        )

        signup = client.post(
            "/auth/signup",
            json={
                "email": "leak@credtest.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Leak Test Co",
            },
        )
        workspace_id = signup.json()["workspace"]["id"]

        encrypted = encrypt_credential(SECRET)
        integration = Integration(
            workspace_id=workspace_id,
            provider=IntegrationProvider.SLACK,
            status=IntegrationStatus.CONNECTED,
            display_name="Slack",
            credential_ciphertext=encrypted.ciphertext,
            credential_key_id=encrypted.key_id,
            credential_hint=encrypted.hint,
        )
        db.add(integration)
        db.flush()
        db.add(
            WorkspaceCapability(
                workspace_id=workspace_id,
                integration_id=integration.id,
                name="send_message",
                enabled=True,
            )
        )
        db.commit()

        used: list[str] = []

        def factory(integ, capability_name):
            # The credential is resolved HERE, inside the closure, exactly as
            # the real adapter does it.
            token = decrypt_credential(
                integ.credential_ciphertext, integ.credential_key_id
            )
            used.append(token)

            def handler(params):
                assert token == SECRET  # the handler really does have it
                return {"ok": True, "channel": params.get("target")}

            return handler

        result = execute_action(
            db=db,
            workspace=db.get(Workspace, workspace_id),
            capability="send_message",
            params={"target": "#general", "text": "hello"},
            handler_factory=factory,
        )
        assert result.outcome == ExecutionOutcome.EXECUTED, result.reason
        assert used == [SECRET], "the handler never received the credential"

        # THE assertion: scan every durable runtime row for the token.
        store = get_store(workspace_id)
        dumped = json.dumps(store.recent_execution()) + json.dumps(store.recent_audit())
        assert SECRET not in dumped, "credential leaked into the runtime execution log"
        assert "xoxb" not in dumped, "a token fragment leaked into durable storage"

    def test_credential_is_absent_from_api_responses(self, client, db):
        """Nothing the frontend receives may contain a credential."""
        from kynd_api.models import Integration, IntegrationProvider, IntegrationStatus

        signup = client.post(
            "/auth/signup",
            json={
                "email": "api@credtest.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "API Cred Co",
            },
        )
        workspace_id = signup.json()["workspace"]["id"]

        encrypted = encrypt_credential(SECRET)
        db.add(
            Integration(
                workspace_id=workspace_id,
                provider=IntegrationProvider.SLACK,
                status=IntegrationStatus.CONNECTED,
                display_name="Slack",
                credential_ciphertext=encrypted.ciphertext,
                credential_key_id=encrypted.key_id,
                credential_hint=encrypted.hint,
            )
        )
        db.commit()

        for path in ("/auth/me", "/workspace", "/workspace/members"):
            body = client.get(path).text
            assert SECRET not in body, f"credential leaked from {path}"
            assert "xoxb-1234" not in body, f"token fragment leaked from {path}"

    def test_credential_is_not_written_to_logs(self, caplog):
        """A token in a log line is a token in every log aggregator forever."""
        with caplog.at_level(logging.DEBUG):
            encrypted = encrypt_credential(SECRET)
            decrypt_credential(encrypted.ciphertext, encrypted.key_id)
        assert SECRET not in caplog.text
        assert "xoxb" not in caplog.text

    def test_model_repr_excludes_the_ciphertext(self):
        """reprs end up in tracebacks and error trackers."""
        from kynd_api.models import Integration, IntegrationProvider

        encrypted = encrypt_credential(SECRET)
        integration = Integration(
            id="int_test",
            workspace_id="ws_test",
            provider=IntegrationProvider.SLACK,
            display_name="Slack",
            credential_ciphertext=encrypted.ciphertext,
            credential_key_id=encrypted.key_id,
        )
        text = repr(integration)
        assert "credential" not in text.lower()
        assert encrypted.key_id not in text
