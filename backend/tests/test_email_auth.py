from fastapi.testclient import TestClient
import pytest

import config
from routers import auth
from server import app
from services.auth_security import hash_password
from services.rate_limit import limiter


@pytest.fixture(autouse=True)
def reset_rate_limits():
    limiter.clear()
    yield
    limiter.clear()


def test_email_signup_requires_verification_before_login(monkeypatch):
    config.db.clear()
    sent = {}

    async def capture_email(email, name, token):
        sent.update(email=email, name=name, token=token)

    monkeypatch.setattr(auth, "send_verification_email", capture_email)

    with TestClient(app) as client:
        signup = client.post(
            "/api/auth/signup",
            json={"name": "Ada Writer", "email": " ADA@Example.com ", "password": "novelDraft42"},
        )
        assert signup.status_code == 202
        assert sent["email"] == "ada@example.com"

        user = config.db._data["users"][0]
        assert user["email_verified"] is False
        assert user["password_hash"].startswith("scrypt$")
        assert "novelDraft42" not in user["password_hash"]

        blocked = client.post(
            "/api/auth/login",
            json={"email": "ada@example.com", "password": "novelDraft42"},
        )
        assert blocked.status_code == 403

        verified = client.post("/api/auth/verify-email", json={"token": sent["token"]})
        assert verified.status_code == 200
        assert client.post("/api/auth/verify-email", json={"token": sent["token"]}).status_code == 400

        login = client.post(
            "/api/auth/login",
            json={"email": "ADA@example.com", "password": "novelDraft42"},
        )
        assert login.status_code == 200
        payload = login.json()
        assert payload["session_token"]
        assert payload["user"]["email_verified"] is True
        assert "password_hash" not in payload["user"]

        me = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {payload['session_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "ada@example.com"
        assert "password_hash" not in me.json()


def test_signup_validates_password_and_login_rejects_bad_credentials(monkeypatch):
    config.db.clear()

    async def capture_email(email, name, token):
        return None

    monkeypatch.setattr(auth, "send_verification_email", capture_email)

    with TestClient(app) as client:
        weak = client.post(
            "/api/auth/signup",
            json={"name": "Test Writer", "email": "writer@example.com", "password": "password"},
        )
        assert weak.status_code == 422

        missing = client.post(
            "/api/auth/login",
            json={"email": "missing@example.com", "password": "wrongPassword1"},
        )
        assert missing.status_code == 401


def test_production_manuscript_creation_requires_auth(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "REQUIRE_AUTH", True)

    with TestClient(app) as client:
        response = client.post(
            "/api/manuscripts",
            json={"title": "Anonymous", "raw_text": "This should not consume quota."},
        )

    assert response.status_code == 401


def test_password_reset_is_single_use_and_invalidates_sessions(monkeypatch):
    config.db.clear()
    sent = {}

    async def capture_reset(email, name, token):
        sent.update(email=email, token=token)

    monkeypatch.setattr(auth, "send_password_reset_email", capture_reset)

    user = {
        "user_id": "user_reset",
        "email": "reset@example.com",
        "name": "Reset Writer",
        "picture": "",
        "password_hash": hash_password("oldPassword1"),
        "email_verified": True,
        "auth_provider": "email",
        "created_at": "2026-01-01T00:00:00+00:00",
    }

    with TestClient(app) as client:
        import asyncio
        asyncio.run(config.db.users.insert_one(user))

        old_login = client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "oldPassword1"},
        )
        old_token = old_login.json()["session_token"]

        requested = client.post("/api/auth/forgot-password", json={"email": user["email"]})
        assert requested.status_code == 202
        assert sent["email"] == user["email"]

        reset = client.post(
            "/api/auth/reset-password",
            json={"token": sent["token"], "password": "newPassword2"},
        )
        assert reset.status_code == 200
        assert client.post(
            "/api/auth/reset-password",
            json={"token": sent["token"], "password": "anotherPassword3"},
        ).status_code == 400
        assert client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {old_token}"}
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "oldPassword1"},
        ).status_code == 401
        assert client.post(
            "/api/auth/login",
            json={"email": user["email"], "password": "newPassword2"},
        ).status_code == 200


def test_forgot_password_does_not_reveal_missing_account(monkeypatch):
    config.db.clear()

    async def should_not_send(*args):
        raise AssertionError("email should not be sent")

    monkeypatch.setattr(auth, "send_password_reset_email", should_not_send)
    with TestClient(app) as client:
        response = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})
    assert response.status_code == 202
    assert response.json()["message"].startswith("If an account exists")


def test_login_rate_limit_returns_retry_after(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(auth, "AUTH_LOGIN_RATE_PER_15_MINUTES", 2)
    payload = {"email": "target@example.com", "password": "wrongPassword1"}

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json=payload).status_code == 401
        assert client.post("/api/auth/login", json=payload).status_code == 401
        limited = client.post("/api/auth/login", json=payload)

    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) >= 1
