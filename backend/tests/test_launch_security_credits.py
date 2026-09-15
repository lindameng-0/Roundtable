import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import config
from routers import auth, billing
from server import app
from services import credits
from services.auth_security import hash_password
from services.rate_limit import limiter
from test_phase3_security import _authenticate, _FakeGoogleClient


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    config.db.clear()
    limiter.clear()
    monkeypatch.setattr(config, "CREDITS_ENABLED", True)
    monkeypatch.setattr(config, "STARTER_CREDITS", 10)
    monkeypatch.setattr(config, "READER_PIPELINE_VERSION", "v2")


def test_google_state_is_bound_to_browser_and_unverified_password_removed(monkeypatch):
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setattr(auth, "GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setattr(auth.httpx, "AsyncClient", _FakeGoogleClient)
    asyncio.run(config.db.users.insert_one({"user_id": "victim", "email": "oauth@example.com",
        "email_verified": False, "password_hash": hash_password("AttackerPass123"), "auth_provider": "email"}))
    with TestClient(app) as original, TestClient(app) as other:
        start = original.get("/api/auth/google/login", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        assert "httponly" in start.headers["set-cookie"].lower()
        path = f"/api/auth/google/callback?code=mock&state={state}"
        rejected = other.get(path, follow_redirects=False)
        assert "invalid_state" in rejected.headers["location"]
        assert "session_token" not in rejected.headers.get("set-cookie", "")
        accepted = original.get(path, follow_redirects=False)
        assert "session_token" in accepted.headers["set-cookie"]
        assert other.post("/api/auth/login", json={"email": "oauth@example.com", "password": "AttackerPass123"}).status_code == 401
        assert "invalid_state" in original.get(path, follow_redirects=False).headers["location"]


def test_quota_removed_and_budget_cannot_be_changed():
    with TestClient(app) as client:
        _authenticate(client)
        made = client.post("/api/manuscripts", json={"raw_text": "word " * 30001, "cost_limit_usd": 1000})
        assert made.status_code == 200, made.text
        assert made.json()["cost_limit_usd"] == 0
        mid = made.json()["id"]
        assert client.patch(f"/api/manuscripts/{mid}/budget", json={"cost_limit_usd": 0}).status_code == 410
        assert client.post("/api/config/model", json={"provider": "gemini", "model": "gemini-2.5-pro"}).status_code == 403
        assert client.get("/api/user/usage").json()["available_credits"] == 10


def test_concurrent_reservations_no_overspend_and_idempotent_settlement():
    async def scenario():
        await asyncio.gather(*(credits.ensure_wallet("writer") for _ in range(10)))
        results = await asyncio.gather(*(credits.reserve("writer", 7000, "reading") for _ in range(2)), return_exceptions=True)
        tokens = [r for r in results if isinstance(r, str)]
        assert len(tokens) == 1
        assert sum(isinstance(r, credits.InsufficientCredits) for r in results) == 1
        assert (await credits.balance("writer"))["available_credits"] == 3
        await asyncio.gather(*(credits.settle_token(tokens[0], 0.02) for _ in range(5)))
        balance = await credits.balance("writer")
        assert balance["available_credits"] == 8
        assert balance["reserved_credits"] == 0
    asyncio.run(scenario())


def test_expired_monthly_reservation_does_not_refund_into_new_period():
    async def scenario():
        await credits.ensure_wallet("writer")
        def grant(state):
            state.update(monthly=10000, grant_end=time.time() + 100)
            return {"kind": "monthly"}
        await credits.change("writer", "grant", grant)
        token = await credits.reserve("writer", 5000, "reading")
        def renew(state):
            state.update(monthly=20000, grant_end=time.time() + 200)
            return {"kind": "monthly"}
        await credits.change("writer", "renew", renew)
        await credits.settle_token(token, 0)
        assert (await credits.balance("writer"))["monthly_credits"] == 20
    asyncio.run(scenario())


def test_checkout_ignores_client_price_and_signature_validation(monkeypatch):
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "paddle_test_secret")
    payload = json.dumps({"event_id": "evt_unknown", "event_type": "unused", "data": {}}).encode()
    stamp = str(int(time.time()))
    signature = hmac.new(b"paddle_test_secret", stamp.encode() + b":" + payload, hashlib.sha256).hexdigest()
    with TestClient(app) as client:
        assert client.post("/api/billing/webhook", content=payload, headers={"paddle-signature": "ts=1;h1=bad"}).status_code == 400
        assert client.post("/api/billing/webhook", content=payload, headers={"paddle-signature": f"ts={stamp};h1={signature}"}).status_code == 200
        assert client.post("/api/billing/webhook", content=payload + b" ", headers={"paddle-signature": f"ts={stamp};h1={signature}"}).status_code == 400
        _authenticate(client)
        assert client.post("/api/billing/checkout", json={"item": "arbitrary", "credits": 99999, "amount": 1}).status_code == 400


def test_paid_topup_is_fulfilled_once_across_different_events(monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_TOPUP_100", "pri_pack")
    paid = {"id": "txn_test", "status": "completed", "customer_id": "ctm_test", "origin": "api",
            "items": [{"price": {"id": "pri_pack"}, "quantity": 1}],
            "custom_data": {"roundtable_user_id": "writer", "item": "topup_100"}}
    async def fake_paddle(method, path, data=None):
        return paid
    monkeypatch.setattr(billing, "paddle", fake_paddle)
    async def scenario():
        await credits.ensure_wallet("writer")
        def customer(state):
            state["customer"] = "ctm_test"
            return {"kind": "customer"}
        await credits.change("writer", "customer", customer)
        for eid in ("evt_first", "evt_replay"):
            await billing.fulfill({"event_id": eid, "event_type": "transaction.completed", "data": {"id": "txn_test"}})
        assert (await credits.balance("writer"))["topup_credits"] == 100
        paid["status"] = "paid"
        paid["id"] = "txn_other"
        await billing.fulfill({"event_id": "delayed", "event_type": "transaction.completed", "data": {"id": "txn_other"}})
        assert (await credits.balance("writer"))["topup_credits"] == 100
    asyncio.run(scenario())


def test_insufficient_credit_stops_provider_call(monkeypatch):
    import litellm
    from services.llm_gateway import structured_completion
    from services.model_routing import ModelRoute
    monkeypatch.setattr(config, "MOCK_LLM", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    called = []
    async def completion(**kwargs):
        called.append(True)
        raise AssertionError("Provider must not run")
    monkeypatch.setattr(litellm, "acompletion", completion)
    async def scenario():
        await credits.ensure_wallet("writer")
        await credits.reserve("writer", 10000, "other work")
        with pytest.raises(credits.InsufficientCredits):
            await structured_completion(route=ModelRoute("openai", "gpt-5.6-luna"), role="genre",
                system_prompt="test", user_prompt="test", billing_user_id="writer")
        assert not called
    asyncio.run(scenario())


def test_out_of_order_renewal_and_cancellation_preserve_purchased_credits(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setenv("PADDLE_PRICE_PRO", "pri_pro")
    now = int(time.time())
    iso = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    sub = {"id": "sub_test", "customer_id": "ctm_test", "created_at": iso(now - 100),
           "updated_at": iso(now), "status": "active",
           "current_billing_period": {"starts_at": iso(now - 10), "ends_at": iso(now + 1000)},
           "custom_data": {"roundtable_user_id": "writer"}, "items": [{"price": {"id": "pri_pro"}}]}
    def transaction(name, start, end):
        return {"id": name, "status": "completed", "origin": "subscription_recurring", "subscription_id": "sub_test",
                "customer_id": "ctm_test", "custom_data": {"roundtable_user_id": "writer"},
                "items": [{"quantity": 1, "price": {"id": "pri_pro"}}],
                "billing_period": {"starts_at": iso(start), "ends_at": iso(end)}}
    transactions = {"new": transaction("new", now - 10, now + 1000), "old": transaction("old", now - 2000, now - 1000)}
    async def fake_paddle(method, path, data=None):
        return sub if path.startswith("subscriptions/") else transactions[path.split("/")[1]]
    monkeypatch.setattr(billing, "paddle", fake_paddle)
    async def scenario():
        await credits.ensure_wallet("writer")
        def customer(state):
            state.update(customer="ctm_test", topup=5000)
            return {"kind": "customer"}
        await credits.change("writer", "customer", customer)
        for name in ("new", "old", "new"):
            await billing.fulfill({"event_id": name, "event_type": "transaction.completed", "data": {"id": name}})
        assert (await credits.balance("writer"))["monthly_credits"] == 200
        sub["status"] = "canceled"
        sub["updated_at"] = iso(now + 1)
        await billing.sync_subscription(sub)
        state = await credits.balance("writer")
        assert state["topup_credits"] == 5
        assert state["plan"] == "free"
        sub["status"] = "active"
        sub["updated_at"] = iso(now)
        await billing.sync_subscription(sub)
        assert (await credits.balance("writer"))["plan"] == "free"
    asyncio.run(scenario())


def test_failed_provider_call_releases_credits(monkeypatch):
    import litellm
    from services.llm_gateway import structured_completion
    from services.model_routing import ModelRoute
    monkeypatch.setattr(config, "MOCK_LLM", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    async def failed(**kwargs):
        raise RuntimeError("Provider unavailable")
    monkeypatch.setattr(litellm, "acompletion", failed)
    async def scenario():
        with pytest.raises(RuntimeError, match="Provider unavailable"):
            await structured_completion(route=ModelRoute("openai", "gpt-5.6-luna"), role="genre",
                system_prompt="test", user_prompt="test", billing_user_id="writer")
        state = await credits.balance("writer")
        assert state["available_credits"] == 10
        assert state["reserved_credits"] == 0
    asyncio.run(scenario())


def test_checkout_uses_catalog_and_resumes_without_duplicate_transaction(monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_WRITER_V2", "pri_pro")
    calls, transactions = [], {}
    async def fake_paddle(method, path, data=None):
        calls.append((method, path, data))
        if path == "prices/pri_pro":
            return {"status": "active", "unit_price": {"amount": "1500", "currency_code": "USD"},
                    "billing_cycle": {"interval": "month", "frequency": 1}, "trial_period": None}
        if path == "customers" and method == "GET":
            return []
        if path == "customers":
            return {"id": "ctm_test"}
        if path == "subscriptions":
            return []
        if path == "transactions" and method == "POST":
            transactions["txn_test"] = {"id": "txn_test", "status": "draft", **data}
            return transactions["txn_test"]
        if path == "transactions/txn_test" and method == "PATCH":
            transactions["txn_test"]["status"] = "canceled"
            return transactions["txn_test"]
        if path == "transactions/txn_test":
            return transactions["txn_test"]
        raise AssertionError(path)
    monkeypatch.setattr(billing, "paddle", fake_paddle)
    with TestClient(app) as client:
        _authenticate(client)
        for _ in range(2):
            response = client.post("/api/billing/checkout", json={"item": "pro", "amount": 1, "credits": 99999})
            assert response.status_code == 200, response.text
            assert response.json()["transaction_id"] == "txn_test"
        posts = [c for c in calls if c[:2] == ("POST", "transactions")]
        assert len(posts) == 1
        assert posts[0][2]["items"] == [{"price_id": "pri_pro", "quantity": 1}]
        assert posts[0][2]["custom_data"]["roundtable_user_id"] == "security-user"
        assert client.post("/api/billing/checkout/cancel").status_code == 200
        assert not client.get("/api/billing/balance").json()["pending_checkout"]


def test_paddle_refund_is_idempotent_and_reversal_restores_credits(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setenv("PADDLE_PRICE_TOPUP_100", "pri_pack")
    transaction = {"id": "txn_refund", "customer_id": "ctm_test", "currency_code": "USD",
        "custom_data": {"roundtable_user_id": "writer"}, "items": [{"price": {"id": "pri_pack"}, "quantity": 1}],
        "details": {"totals": {"grand_total": "1200"}}}
    adjustments = [{"id": "adj_test", "status": "approved", "action": "refund", "currency_code": "USD", "totals": {"total": "600"}}]
    async def fake_paddle(method, path, data=None):
        return transaction if path.startswith("transactions/") else adjustments
    monkeypatch.setattr(billing, "paddle", fake_paddle)
    async def scenario():
        await credits.ensure_wallet("writer")
        def customer(state):
            state.update(customer="ctm_test", topup=100000)
            return {"kind": "topup"}
        await credits.change("writer", "paid", customer)
        event = {"event_id": "evt_refund", "occurred_at": datetime.now(timezone.utc).isoformat()}
        adjustment = {"transaction_id": "txn_refund"}
        for _ in range(2):
            await billing.reconcile_adjustment(adjustment, event)
        assert (await credits.balance("writer"))["topup_credits"] == 50
        adjustments[0]["status"] = "reversed"
        event = {"event_id": "evt_reversed", "occurred_at": datetime.now(timezone.utc).isoformat()}
        await billing.reconcile_adjustment(adjustment, event)
        assert (await credits.balance("writer"))["topup_credits"] == 100
    asyncio.run(scenario())


def test_plan_change_waits_for_paid_renewal_before_granting_credits(monkeypatch):
    from datetime import datetime, timezone
    monkeypatch.setenv("PADDLE_PRICE_STUDIO_V2", "pri_studio")
    now = datetime.now(timezone.utc).isoformat()
    sub = {"id": "sub_writer", "customer_id": "ctm_test", "status": "active", "scheduled_change": None,
           "custom_data": {"roundtable_user_id": "security-user"}, "created_at": now, "updated_at": now,
           "items": [{"price": {"id": "pri_studio"}}], "current_billing_period": None}
    patches = []
    async def fake_paddle(method, path, data=None):
        if path.startswith("prices/"):
            return {"status": "active", "unit_price": {"amount": "2900", "currency_code": "USD"},
                    "billing_cycle": {"interval": "month", "frequency": 1}}
        if method == "PATCH":
            patches.append(data)
        return sub
    monkeypatch.setattr(billing, "paddle", fake_paddle)
    with TestClient(app) as client:
        _authenticate(client)
        async def setup():
            await credits.ensure_wallet("security-user")
            def paid(state):
                state.update(customer="ctm_test", subscription="sub_writer", plan="pro", grant_plan="pro",
                             monthly=200000, grant_end=time.time() + 1000)
                return {"kind": "monthly"}
            await credits.change("security-user", "test_paid", paid)
        asyncio.run(setup())
        response = client.post("/api/billing/change-plan", json={"item": "studio"})
        assert response.status_code == 200, response.text
        assert patches == [{"items": [{"price_id": "pri_studio", "quantity": 1}], "proration_billing_mode": "do_not_bill"}]
        balance = client.get("/api/billing/balance").json()
        assert balance["monthly_credits"] == 200
        assert balance["plan"] == "pro" and balance["next_plan"] == "studio"


def test_live_paddle_requires_explicit_enablement(monkeypatch):
    monkeypatch.setenv("PADDLE_API_KEY", "private_test_fixture")
    monkeypatch.setenv("PADDLE_WEBHOOK_SECRET", "private_test_fixture")
    monkeypatch.setenv("PADDLE_ENVIRONMENT", "production")
    monkeypatch.setenv("PADDLE_CLIENT_TOKEN", "live_test_fixture")
    monkeypatch.setenv("PADDLE_LIVE_ENABLED", "false")
    assert not billing.enabled()
    monkeypatch.setenv("PADDLE_LIVE_ENABLED", "true")
    assert billing.enabled()


def test_verification_link_cannot_verify_a_replaced_password(monkeypatch):
    sent = {}
    async def email(address, name, token):
        sent["token"] = token
    monkeypatch.setattr(auth, "send_verification_email", email)
    async def setup():
        user = {"user_id": "pending", "email": "pending@example.com", "email_verified": False,
                "password_hash": hash_password("OriginalPass123")}
        await config.db.users.insert_one(user)
        await auth._issue_verification(user)
        await config.db.users.update_one({"user_id": "pending"}, {"$set": {"password_hash": hash_password("Replacement123")}})
    asyncio.run(setup())
    with TestClient(app) as client:
        response = client.post("/api/auth/verify-email", json={"token": sent["token"]})
        assert response.status_code == 400
    assert not asyncio.run(config.db.users.find_one({"user_id": "pending"}))["email_verified"]
