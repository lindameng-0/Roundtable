import asyncio

import config
from services.cost_control import CostLimitExceeded, budget_status, preflight_estimate, reserve, settle


def _manuscript(limit=0.10):
    return {
        "id": "m-cost", "title": "Cost test", "raw_text": "A short scene. " * 300,
        "sections": [{
            "section_number": 1,
            "paragraph_lines": [{"line": 1, "paragraph_id": "p-000001", "text": "A short scene. " * 300}],
        }],
        "cost_limit_usd": limit, "cost_spent_usd": 0, "cost_reserved_usd": 0,
    }


def test_concurrent_reservations_cannot_overspend():
    async def scenario():
        config.db.clear()
        await config.db.manuscripts.insert_one(_manuscript(limit=0.10))

        async def attempt(index):
            try:
                return await reserve("m-cost", "reader", f"reader:{index}", 0.06)
            except CostLimitExceeded:
                return None

        reservations = await asyncio.gather(attempt(1), attempt(2))
        assert sum(item is not None for item in reservations) == 1
        saved = await config.db.manuscripts.find_one({"id": "m-cost"})
        assert saved["cost_reserved_usd"] == 0.06

    asyncio.run(scenario())


def test_settlement_releases_reservation_and_records_actual_cost():
    async def scenario():
        config.db.clear()
        await config.db.manuscripts.insert_one(_manuscript())
        reservation_id = await reserve("m-cost", "editor", "editor_report", 0.08)
        await settle(reservation_id, 0.031)
        saved = await config.db.manuscripts.find_one({"id": "m-cost"})
        status = await budget_status(saved)
        assert status["reserved_usd"] == 0
        assert status["spent_usd"] == 0.031
        assert status["remaining_usd"] == 0.069

    asyncio.run(scenario())


def test_preflight_breaks_estimate_down_by_expensive_role(monkeypatch):
    async def scenario():
        config.db.clear()
        manuscript = _manuscript(limit=5)
        await config.db.manuscripts.insert_one(manuscript)
        reader = {"id": "r1", "avatar_index": 0}
        monkeypatch.setattr(config, "READER_MODEL_POOL", "anthropic:claude-sonnet-5")
        estimate = await preflight_estimate(manuscript, [reader], "remaining")
        assert estimate["estimated_cost_usd"] > 0
        assert estimate["by_role"]["reader"]["models"] == ["anthropic:claude-sonnet-5"]
        assert "editor" in estimate["by_role"]
        assert estimate["can_start"]

    asyncio.run(scenario())
