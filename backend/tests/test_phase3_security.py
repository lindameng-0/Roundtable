import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

import config
from routers import auth
from server import allow_origins, app
from services.auth_security import hash_opaque_token
from services.rate_limit import limiter


def _authenticate(client: TestClient, user_id="security-user", email="security@example.com"):
    raw_session = f"session-{user_id}"
    asyncio.run(config.db.users.insert_one({
        "user_id": user_id, "email": email, "name": "Security Writer",
        "email_verified": True, "auth_provider": "email",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    asyncio.run(config.db.user_sessions.insert_one({
        "user_id": user_id, "token_hash": hash_opaque_token(raw_session),
        "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }))
    client.cookies.set("session_token", raw_session)


def test_all_costly_manuscript_routes_reject_unauthenticated_callers():
    config.db.clear()
    limiter.clear()
    routes = [
        ("get", "/api/manuscripts/missing/personas"),
        ("post", "/api/manuscripts/missing/personas/regenerate"),
        ("post", "/api/manuscripts/missing/personas/add"),
        ("get", "/api/manuscripts/missing/read-all"),
        ("post", "/api/manuscripts/missing/editor-report"),
        ("post", "/api/manuscripts/missing/editor-report/copy-edit"),
    ]
    with TestClient(app) as client:
        for method, route in routes:
            response = client.post(route, json={}) if method == "post" else client.get(route)
            assert response.status_code == 401, (route, response.text)


def test_ownerless_and_cross_account_manuscripts_are_inaccessible():
    config.db.clear()
    with TestClient(app) as client:
        _authenticate(client)
        asyncio.run(config.db.manuscripts.insert_one({"id": "ownerless", "user_id": None}))
        asyncio.run(config.db.manuscripts.insert_one({"id": "other", "user_id": "other-user"}))
        assert client.get("/api/manuscripts/ownerless").status_code == 403
        assert client.get("/api/manuscripts/other").status_code == 403


def test_upload_rejects_spoofed_signature_and_oversize_request():
    config.db.clear()
    with TestClient(app) as client:
        _authenticate(client)
        spoofed = client.post(
            "/api/manuscripts/upload",
            files={"file": ("book.pdf", b"this is not a pdf", "application/pdf")},
        )
        assert spoofed.status_code == 400

        oversized = client.post(
            "/api/manuscripts/upload",
            files={"file": ("book.txt", b"short", "text/plain")},
            headers={"Content-Length": str((config.MAX_UPLOAD_MB + 2) * 1024 * 1024)},
        )
        assert oversized.status_code == 413


class _FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = "ok"

    def json(self):
        return self._payload


class _FakeGoogleClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        return _FakeResponse({"access_token": "google-access"})

    async def get(self, *args, **kwargs):
        return _FakeResponse({
            "email": "oauth@example.com", "name": "OAuth Writer",
            "picture": "", "verified_email": True,
        })


def test_oauth_state_is_durable_single_use_and_callback_has_no_token(monkeypatch):
    config.db.clear()
    limiter.clear()
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(auth, "FRONTEND_URL", "https://roundtable.works")
    monkeypatch.setattr(auth.httpx, "AsyncClient", _FakeGoogleClient)

    with TestClient(app) as client:
        start = client.get("/api/auth/google/login", follow_redirects=False)
        assert start.status_code == 302
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        stored = config.db._data["oauth_states"][0]
        assert stored["token_hash"] == hash_opaque_token(state)
        assert state not in str(stored)

        callback = client.get(
            f"/api/auth/google/callback?code=valid-code&state={state}", follow_redirects=False
        )
        assert callback.status_code == 302
        assert callback.headers["location"] == "https://roundtable.works/auth/callback"
        assert "session_token" not in callback.headers["location"]
        assert "httponly" in callback.headers["set-cookie"].lower()
        assert not config.db._data["oauth_states"]
        session = config.db._data["user_sessions"][0]
        assert session.get("token_hash")
        assert "session_token" not in session

        replay = client.get(
            f"/api/auth/google/callback?code=valid-code&state={state}", follow_redirects=False
        )
        assert "invalid_state" in replay.headers["location"]


def test_production_cookie_requests_require_the_frontend_origin(monkeypatch):
    config.db.clear()
    previous = os.environ.get("ENVIRONMENT")
    os.environ["ENVIRONMENT"] = "production"
    try:
        with TestClient(app) as client:
            _authenticate(client)
            rejected = client.get("/api/manuscripts")
            allowed = client.get("/api/manuscripts", headers={"Origin": allow_origins[0]})
        assert rejected.status_code == 403
        assert allowed.status_code == 200, allowed.text
    finally:
        if previous is None:
            os.environ.pop("ENVIRONMENT", None)
        else:
            os.environ["ENVIRONMENT"] = previous
