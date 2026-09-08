import asyncio

import pytest

import config
from routers import billing
from services import credits


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "STARTER_CREDITS", 50)
    monkeypatch.setattr(credits.time, "time", lambda: 150)


def test_rollover_caps_at_new_allowance_and_lasts_one_cycle():
    state = credits.normalize({})
    credits.grant_monthly(state, 450000, 100, 200, "studio", "sub", rollover=True)
    state["monthly"] = 300000
    credits.grant_monthly(state, 200000, 200, 300, "pro", "sub", rollover=True)
    assert (state["monthly"], state["rollover"]) == (200000, 200000)
    state["monthly"] = 40000
    credits.grant_monthly(state, 200000, 300, 400, "pro", "sub", rollover=True)
    assert state["rollover"] == 40000
    credits.grant_monthly(state, 450000, 200, 300, "studio", "sub", rollover=True)
    assert (state["monthly"], state["rollover"]) == (200000, 40000)


def test_expiry_and_delayed_contiguous_renewal(monkeypatch):
    state = credits.normalize({})
    credits.grant_monthly(state, 200000, 100, 200, "pro", "sub", rollover=True)
    state["monthly"] = 80000
    monkeypatch.setattr(credits.time, "time", lambda: 210)
    state = credits.normalize(state)
    assert state["monthly"] == state["rollover"] == 0
    credits.grant_monthly(state, 200000, 200, 300, "pro", "sub", rollover=True)
    assert state["rollover"] == 80000
    monkeypatch.setattr(credits.time, "time", lambda: 310)
    assert credits.normalize(state)["rollover"] == 0


@pytest.mark.parametrize("start,subscription,legacy", [(201, "sub", False), (200, "other", False), (200, "sub", True)])
def test_no_rollover_across_gap_subscription_or_legacy(start, subscription, legacy):
    state = credits.normalize({})
    credits.grant_monthly(state, 200000, 100, 200, "pro", "sub", rollover=not legacy)
    credits.grant_monthly(state, 200000, start, 300, "pro", subscription, rollover=True)
    assert state["rollover"] == 0


def test_rollover_spent_first_and_expired_hold_not_restored(monkeypatch):
    async def scenario():
        await credits.ensure_wallet("writer")
        def grant(state):
            state.update(rollover=20000, rollover_end=200, monthly=100000, grant_end=200)
            return {}
        await credits.change("writer", "grant", grant)
        token = await credits.reserve("writer", 25000, "reading")
        balance = await credits.balance("writer")
        assert balance["rollover_credits"] == 0
        assert balance["monthly_credits"] == 95
        monkeypatch.setattr(credits.time, "time", lambda: 210)
        await credits.settle_token(token, 0)
        balance = await credits.balance("writer")
        assert balance["available_credits"] == 50
        assert balance["reserved_credits"] == 0
    asyncio.run(scenario())


def test_starter_upgrade_is_once_and_preserves_spending(monkeypatch):
    async def scenario():
        monkeypatch.setattr(config, "STARTER_CREDITS", 10)
        await credits.ensure_wallet("existing")
        token = await credits.reserve("existing", 7000, "reading")
        await credits.finish("existing", token.split(":")[2], 7000)
        monkeypatch.setattr(config, "STARTER_CREDITS", 50)
        await asyncio.gather(*(credits.ensure_wallet("existing") for _ in range(10)))
        assert (await credits.balance("existing"))["starter_credits"] == 43
        assert (await credits.balance("new"))["starter_credits"] == 50
    asyncio.run(scenario())


def test_catalog_prices_and_legacy_entitlements(monkeypatch):
    monkeypatch.setenv("PADDLE_PRICE_STUDIO", "pri_old")
    monkeypatch.setenv("PADDLE_PRICE_STUDIO_V2", "pri_new")
    assert billing.price_item("pri_old")[1]["credits"] == 600
    assert billing.price_item("pri_new")[1]["credits"] == 450
    assert billing.price_item("") == (None, None)
    catalog = asyncio.run(billing.catalog())
    assert catalog["catalog_version"] == 2
    assert [(p["cents"], p["credits"]) for p in catalog["items"]] == [
        (1500, 200), (2900, 450), (1000, 100), (2000, 220), (3500, 400)]
