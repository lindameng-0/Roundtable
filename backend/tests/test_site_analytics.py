from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import config
from server import app
from services.auth_security import hash_opaque_token
from services.rate_limit import limiter


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    config.db.clear()
    limiter.clear()
    monkeypatch.setenv("OWNER_EMAIL", "itsyuko0o1@gmail.com")
    monkeypatch.delenv("OWNER_USER_ID", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "https://roundtable.works")
    yield
    config.db.clear()
    limiter.clear()


def session(client, email="itsyuko0o1@gmail.com", verified=True, expired=False):
    config.db._data["users"].append({"user_id": "owner-test", "email": email, "email_verified": verified})
    config.db._data["user_sessions"].append({
        "user_id": "owner-test", "token_hash": hash_opaque_token("test-token"),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=-1 if expired else 1)).isoformat(),
    })
    client.cookies.set("session_token", "test-token")


@pytest.mark.parametrize("email,verified,expired,status", [
    ("itsyuko0o1@gmail.com", True, False, 200),
    ("ITSYUKO0O1@gmail.com", True, False, 200),
    ("someone@example.com", True, False, 403),
    ("itsyuko0o1@gmail.com", False, False, 403),
    ("itsyuko0o1@gmail.com", True, True, 401),
])
def test_owner_boundary(email, verified, expired, status):
    with TestClient(app) as client:
        assert client.get("/api/analytics/summary").status_code == 401
        session(client, email, verified, expired)
        result = client.get("/api/analytics/summary")
        assert result.status_code == status
        if status == 200:
            assert result.headers["cache-control"] == "private, no-store"
            assert result.headers["x-robots-tag"] == "noindex, nofollow"
            assert client.get("/api/auth/me").json()["is_owner"] is True


def test_pinned_owner_id(monkeypatch):
    monkeypatch.setenv("OWNER_USER_ID", "different-account")
    with TestClient(app) as client:
        session(client)
        assert client.get("/api/analytics/summary").status_code == 403


def test_collection_and_exact_summary():
    with TestClient(app) as client:
        headers = {"origin": "https://roundtable.works"}
        for _ in range(3):
            assert client.post("/api/analytics/events", headers=headers, json={"path": "/", "source": "chatgpt"}).status_code == 204
        client.post("/api/analytics/events", headers=headers, json={"path": "/", "event": "signup_click"})
        session(client)
        result = client.get("/api/analytics/summary?days=7").json()
        assert result["pageviews"] == 3
        assert result["signup_clicks"] == 1
        assert result["sources"] == {"chatgpt": 3}
        assert len(result["daily"]) == 7
        assert sum(day["views"] for day in result["daily"]) == 3
        assert result["totals"]["verified_accounts"] == 1
        assert len(config.db._data["site_analytics"]) == 2
        assert set(config.db._data["site_analytics"][0]) == {"day", "path", "source", "event", "count"}
        assert client.get("/api/analytics/summary?days=999").status_code == 422


def test_private_urls_extra_data_origins_and_privacy_signals():
    with TestClient(app) as client:
        url = "/api/analytics/events"
        headers = {"origin": "https://roundtable.works"}
        for body in [{"path": "/read/private-id"}, {"path": "/?email=private@example.com"}, {"path": "/", "email": "secret"}, {"path": "/", "source": "https://example.com/private"}]:
            assert client.post(url, headers=headers, json=body).status_code == 422
        assert client.post(url, json={"path": "/"}).status_code == 403
        assert client.post(url, headers={"origin": "https://evil.example"}, json={"path": "/"}).status_code == 403
        for signal in ["dnt", "sec-gpc"]:
            assert client.post(url, headers={**headers, signal: "1"}, json={"path": "/"}).status_code == 204
        assert not config.db._data.get("site_analytics")


def test_window_filter_and_rate_limit():
    config.db._data["site_analytics"] = [{"day": "2020-01-01", "path": "/", "source": "direct", "event": "pageview", "count": 100}]
    with TestClient(app) as client:
        session(client)
        assert client.get("/api/analytics/summary").json()["pageviews"] == 0
        for _ in range(60):
            assert client.post("/api/analytics/events", headers={"origin": "https://roundtable.works"}, json={"path": "/"}).status_code == 204
        assert client.post("/api/analytics/events", headers={"origin": "https://roundtable.works"}, json={"path": "/"}).status_code == 429
        assert len(config.db._data["site_analytics"]) == 1
