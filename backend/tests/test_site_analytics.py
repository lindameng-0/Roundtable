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
    monkeypatch.setattr(config, "ANALYTICS_HASH_SECRET", "test-analytics-secret")
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
            assert client.post("/api/analytics/events", headers=headers, json={"path": "/beta-readers", "source": "chatgpt"}).status_code == 204
        client.post("/api/analytics/events", headers=headers, json={"path": "/", "event": "signup_click"})
        session(client)
        result = client.get("/api/analytics/summary?days=7").json()
        assert result["pageviews"] == 3
        assert result["signup_clicks"] == 1
        assert result["unique_signup_click_visitors"] == 1
        assert result["funnel"]["signup_pageviews"] == 0
        assert result["funnel"]["signup_clicks"] == 1
        assert result["sources"] == {"chatgpt": 3}
        assert len(result["daily"]) == 7
        assert sum(day["views"] for day in result["daily"]) == 3
        assert result["totals"]["verified_accounts"] == 0
        assert len(config.db._data["site_analytics"]) == 2
        assert set(config.db._data["site_analytics"][0]) == {"day", "path", "source", "event", "count"}
        assert client.get("/api/analytics/summary?days=999").status_code == 422


def test_funnel_counts_events_and_deduplicates_network_sources(monkeypatch):
    identities = iter(["198.51.100.10", "198.51.100.10", "203.0.113.20"])
    monkeypatch.setattr("services.site_analytics.client_ip", lambda _request: next(identities))
    headers = {"origin": "https://roundtable.works"}
    with TestClient(app) as client:
        for event in ["signup_click", "signup_click", "signup_click"]:
            assert client.post("/api/analytics/events", headers=headers, json={"path": "/", "event": event}).status_code == 204
        session(client)
        result = client.get("/api/analytics/summary").json()
        assert result["signup_clicks"] == 3
        assert result["unique_signup_click_visitors"] == 2
        assert result["unique_signup_clicks_by_path"] == {"/": 2}
        assert all("visitor_hash" not in str(value) for value in result.values())
        stored = {row["visitor_hash"] for row in config.db._data["site_analytics_visitors"]}
        assert "198.51.100.10" not in stored and "203.0.113.20" not in stored
        assert all(len(value) == 64 for value in stored)


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


@pytest.mark.parametrize("event", ["pageview", "signup_click"])
def test_owner_traffic_is_excluded_even_if_client_sends_it(event):
    with TestClient(app) as client:
        session(client)
        response = client.post("/api/analytics/events", headers={"origin": "https://roundtable.works"},
                               json={"path": "/pricing", "event": event})
        assert response.status_code == 204
        summary = client.get("/api/analytics/summary").json()
        assert summary["pageviews"] == summary["signup_clicks"] == 0
        assert not config.db._data.get("site_analytics")


@pytest.mark.parametrize("email,verified,expired", [
    ("visitor@example.com", True, False),
    ("itsyuko0o1@gmail.com", False, False),
    ("itsyuko0o1@gmail.com", True, True),
])
def test_non_owner_and_expired_sessions_still_count(email, verified, expired):
    with TestClient(app) as client:
        session(client, email, verified, expired)
        response = client.post("/api/analytics/events", headers={"origin": "https://roundtable.works"},
                               json={"path": "/", "event": "signup_click"})
        assert response.status_code == 204
        assert config.db._data["site_analytics"][0]["count"] == 1
        assert set(config.db._data["site_analytics"][0]) == {"day", "path", "source", "event", "count"}


def test_internal_accounts_and_their_manuscripts_are_excluded_from_totals():
    with TestClient(app) as client:
        session(client)
        config.db._data['users'].extend([
            {'user_id': 'internal-gmail', 'email': 'lndmeng@gmail.com', 'email_verified': True},
            {'user_id': 'internal-ucla', 'email': 'lndmeng@g.ucla.edu', 'email_verified': False},
            {'user_id': 'visitor', 'email': 'visitor@example.com', 'email_verified': True},
            {'user_id': 'unverified', 'email': 'new@example.com', 'email_verified': False},
            {'user_id': 'similar', 'email': 'lndmeng+reader@gmail.com', 'email_verified': True},
        ])
        config.db._data['manuscripts'][:] = [
            {'id': 'owner-draft', 'user_id': 'owner-test'},
            {'id': 'gmail-draft', 'user_id': 'internal-gmail'},
            {'id': 'gmail-draft-2', 'user_id': 'internal-gmail'},
            {'id': 'ucla-draft', 'user_id': 'internal-ucla'},
            {'id': 'visitor-draft', 'user_id': 'visitor'},
            {'id': 'guest-draft', 'user_id': None},
            {'id': 'similar-draft', 'user_id': 'similar'},
        ]
        config.db._data['editor_reports'][:] = [{'id': 'report', 'manuscript_id': 'owner-draft'}]
        for period in (7, 30, 90):
            result = client.get(f'/api/analytics/summary?days={period}')
            assert result.status_code == 200
            assert result.json()['totals'] == {'verified_accounts': 2, 'manuscripts': 3, 'reports': 1}
        # Dashboard filtering must not delete or modify any account or manuscript.
        assert len(config.db._data['users']) == 6
        assert len(config.db._data['manuscripts']) == 7
        config.db._data['manuscripts'].append({'id': 'later-internal', 'user_id': 'internal-ucla'})
        assert client.get('/api/analytics/summary').json()['totals']['manuscripts'] == 3


def test_totals_count_visitors_when_excluded_accounts_do_not_exist(monkeypatch):
    monkeypatch.setenv('OWNER_EMAIL', 'real-owner@example.com')
    with TestClient(app) as client:
        session(client, email='real-owner@example.com')
        config.db._data['manuscripts'][:] = [{'id': 'draft', 'user_id': 'owner-test'}]
        assert client.get('/api/analytics/summary').json()['totals'] == {
            'verified_accounts': 1, 'manuscripts': 1, 'reports': 0,
        }
