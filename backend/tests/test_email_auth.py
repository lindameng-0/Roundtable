from fastapi.testclient import TestClient

import config
from routers import auth
from server import app


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
