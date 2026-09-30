"""Authentication tests.

The exit gate for Phase 1: a real person can sign up, log in, log out, and log
back in, against real Postgres, with the session surviving an API restart.
"""

from __future__ import annotations

from sqlalchemy import select, text

from kynd_api.models import Membership, Role, SessionToken, User, Workspace
from kynd_api.security import passwords
from tests.conftest import signup_user


class TestSignup:
    def test_creates_user_workspace_and_owner_membership(self, client, db):
        body = signup_user(client, email="franco@kynd.io", workspace_name="Kynd")

        assert body["user"]["email"] == "franco@kynd.io"
        assert body["workspace"]["name"] == "Kynd"
        assert body["workspace"]["slug"] == "kynd"
        assert body["role"] == "OWNER"

        user = db.execute(
            select(User).where(User.email_normalized == "franco@kynd.io")
        ).scalar_one()
        workspace = db.execute(select(Workspace)).scalar_one()
        membership = db.execute(select(Membership)).scalar_one()

        assert membership.user_id == user.id
        assert membership.workspace_id == workspace.id
        assert membership.role == Role.OWNER

    def test_password_is_never_stored_in_plaintext(self, client, db):
        secret = "a-very-secret-passphrase-42"
        signup_user(client, email="hash@example.com", password=secret)

        user = db.execute(
            select(User).where(User.email_normalized == "hash@example.com")
        ).scalar_one()

        assert secret not in user.password_hash
        assert user.password_hash.startswith("$argon2id$")
        assert passwords.verify_password(user.password_hash, secret)

        # Nowhere else in the row either. A future column that accidentally
        # captured the raw password would fail here rather than in production.
        row = db.execute(
            text("SELECT * FROM users WHERE email_normalized = :e"),
            {"e": "hash@example.com"},
        ).mappings().one()
        for column, value in row.items():
            if isinstance(value, str):
                assert secret not in value, f"password leaked into users.{column}"

    def test_response_never_contains_password_hash(self, client):
        body = signup_user(client)
        assert "password" not in str(body).lower()

    def test_sets_httponly_session_cookie(self, client):
        response = client.post(
            "/auth/signup",
            json={
                "email": "cookie@example.com",
                "password": "correct-horse-battery-staple",
                "workspace_name": "Cookie Co",
            },
        )
        assert response.status_code == 201
        set_cookie = response.headers["set-cookie"]
        assert "kynd_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Path=/" in set_cookie

    def test_duplicate_email_is_rejected(self, client):
        signup_user(client, email="dupe@example.com")
        response = client.post(
            "/auth/signup",
            json={
                "email": "dupe@example.com",
                "password": "another-long-password-here",
                "workspace_name": "Second",
            },
        )
        assert response.status_code == 409

    def test_email_is_case_insensitive_for_uniqueness(self, client):
        signup_user(client, email="Case@Example.com")
        response = client.post(
            "/auth/signup",
            json={
                "email": "case@example.COM",
                "password": "another-long-password-here",
                "workspace_name": "Second",
            },
        )
        assert response.status_code == 409, "same human, second account created"

    def test_short_password_is_rejected(self, client):
        response = client.post(
            "/auth/signup",
            json={
                "email": "short@example.com",
                "password": "tiny",
                "workspace_name": "Tiny",
            },
        )
        assert response.status_code == 422

    def test_failed_signup_creates_no_partial_rows(self, client, db):
        client.post(
            "/auth/signup",
            json={
                "email": "partial@example.com",
                "password": "short",
                "workspace_name": "Ghost Workspace",
            },
        )
        assert db.execute(select(User)).scalars().all() == []
        assert db.execute(select(Workspace)).scalars().all() == []

    def test_colliding_workspace_names_get_distinct_slugs(self, client):
        first = signup_user(client, email="a@example.com", workspace_name="Acme")
        second = signup_user(client, email="b@example.com", workspace_name="Acme")
        assert first["workspace"]["slug"] == "acme"
        assert second["workspace"]["slug"] == "acme-2"


class TestLogin:
    def test_correct_credentials_succeed(self, client):
        signup_user(client, email="login@example.com", password="the-right-password-1")
        client.post("/auth/logout")

        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "the-right-password-1"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "login@example.com"
        assert response.json()["role"] == "OWNER"

    def test_wrong_password_is_rejected(self, client):
        signup_user(client, email="login@example.com", password="the-right-password-1")
        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "the-wrong-password-1"},
        )
        assert response.status_code == 401

    def test_unknown_email_gives_the_same_error_as_wrong_password(self, client):
        signup_user(client, email="real@example.com", password="the-right-password-1")

        wrong_password = client.post(
            "/auth/login",
            json={"email": "real@example.com", "password": "nope-nope-nope-nope"},
        )
        unknown_email = client.post(
            "/auth/login",
            json={"email": "ghost@example.com", "password": "nope-nope-nope-nope"},
        )

        # Identical status AND identical body: anything else is a free oracle
        # telling an attacker which addresses have accounts.
        assert wrong_password.status_code == unknown_email.status_code == 401
        assert wrong_password.json() == unknown_email.json()

    def test_login_is_rate_limited(self, client):
        signup_user(client, email="brute@example.com", password="the-right-password-1")
        statuses = [
            client.post(
                "/auth/login",
                json={"email": "brute@example.com", "password": f"wrong-{i}-aaaaaaaa"},
            ).status_code
            for i in range(15)
        ]
        assert 429 in statuses, "brute force was never throttled"

    def test_successful_login_clears_the_throttle(self, client):
        signup_user(client, email="human@example.com", password="the-right-password-1")
        for _ in range(4):
            client.post(
                "/auth/login",
                json={"email": "human@example.com", "password": "mistyped-again-x"},
            )
        ok = client.post(
            "/auth/login",
            json={"email": "human@example.com", "password": "the-right-password-1"},
        )
        assert ok.status_code == 200


class TestSession:
    def test_me_requires_authentication(self, client):
        assert client.get("/auth/me").status_code == 401

    def test_me_returns_user_workspace_and_permissions(self, client, owner):
        response = client.get("/auth/me")
        assert response.status_code == 200
        body = response.json()

        assert body["user"]["email"] == "owner@example.com"
        assert body["role"] == "OWNER"
        assert len(body["workspaces"]) == 1
        # An OWNER holds every permission, including the two only they hold.
        assert "workspace:delete" in body["permissions"]
        assert "billing:manage" in body["permissions"]

    def test_logout_revokes_the_session_server_side(self, client, db, owner):
        assert client.get("/auth/me").status_code == 200

        assert client.post("/auth/logout").status_code == 200
        assert client.get("/auth/me").status_code == 401

        session_row = db.execute(select(SessionToken)).scalar_one()
        assert session_row.revoked_at is not None

    def test_a_stolen_cookie_stops_working_after_logout(self, client, owner):
        """Revocation is server-side, so an attacker holding the cookie loses too."""
        stolen = client.cookies.get("kynd_session")
        assert stolen

        client.post("/auth/logout")

        # Replay the captured cookie value on a clean request.
        client.cookies.clear()
        client.cookies.set("kynd_session", stolen)
        assert client.get("/auth/me").status_code == 401

    def test_only_the_token_hash_is_stored(self, client, db, owner):
        raw = client.cookies.get("kynd_session")
        session_row = db.execute(select(SessionToken)).scalar_one()

        assert session_row.token_hash != raw
        assert len(session_row.token_hash) == 64  # sha256 hex
        assert raw not in session_row.token_hash

    def test_forged_token_is_rejected(self, client, owner):
        client.cookies.clear()
        client.cookies.set("kynd_session", "totally-made-up-token-value")
        assert client.get("/auth/me").status_code == 401

    def test_session_survives_a_full_api_restart(self, client, owner):
        """THE Phase 1 exit gate.

        Sessions live in Postgres, not in process memory, so a redeploy does not
        sign every customer out. Proven by building a brand-new app instance —
        a new process's worth of in-memory state — and reusing the cookie.
        """
        from fastapi.testclient import TestClient

        from kynd_api.main import create_app

        cookie = client.cookies.get("kynd_session")

        with TestClient(create_app()) as fresh_client:
            fresh_client.cookies.set("kynd_session", cookie)
            response = fresh_client.get("/auth/me")

        assert response.status_code == 200
        assert response.json()["user"]["email"] == "owner@example.com"

    def test_logout_all_revokes_every_session(self, client, db, owner):
        from fastapi.testclient import TestClient

        from kynd_api.main import create_app

        # A second device.
        with TestClient(create_app()) as other_device:
            other_device.post(
                "/auth/login",
                json={
                    "email": "owner@example.com",
                    "password": "correct-horse-battery-staple",
                },
            )
            assert other_device.get("/auth/me").status_code == 200
            second_cookie = other_device.cookies.get("kynd_session")

        assert client.post("/auth/logout-all").status_code == 200

        with TestClient(create_app()) as replay:
            replay.cookies.set("kynd_session", second_cookie)
            assert replay.get("/auth/me").status_code == 401


class TestHealth:
    def test_health_is_public(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_readiness_checks_the_database(self, client):
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json()["database"] == "ok"

    def test_every_response_carries_a_request_id(self, client):
        response = client.get("/health")
        assert response.headers.get("X-Request-ID")
