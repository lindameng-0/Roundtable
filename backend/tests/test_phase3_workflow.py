import asyncio

import config
from services.workflow import ensure_task_ledger, summarize_usage, task_id, update_task, workflow_status


def _manuscript():
    return {
        "id": "m-phase3",
        "sections": [
            {"section_number": 1, "paragraph_lines": [{"line": 1, "paragraph_id": "p-000001", "text": "One"}]},
            {"section_number": 2, "paragraph_lines": [{"line": 2, "paragraph_id": "p-000002", "text": "Two"}]},
        ],
    }


def _readers():
    return [
        {"id": "r1", "name": "Aisha", "avatar_index": 0},
        {"id": "r2", "name": "Mara", "avatar_index": 1},
    ]


def test_ledger_is_deterministic_and_reconciles_saved_reactions(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "READER_MODEL_POOL", "anthropic:claude-sonnet-5,openai:gpt-5.6-luna")
    asyncio.run(config.db.reader_reactions.insert_one({
        "id": "reaction-1", "manuscript_id": "m-phase3", "reader_id": "r1",
        "reader_name": "Aisha", "section_number": 1, "response_json": {},
    }))

    first = asyncio.run(ensure_task_ledger(_manuscript(), _readers()))
    second = asyncio.run(ensure_task_ledger(_manuscript(), _readers()))
    assert len(first) == len(second) == 4
    assert len({row["id"] for row in first}) == 4
    assert next(row for row in first if row["reader_id"] == "r1" and row["section_number"] == 1)["status"] == "completed"
    assert next(row for row in first if row["reader_id"] == "r2")["planned_provider"] == "openai"


def test_failed_task_remains_retryable_and_attempts_increment(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "READER_MODEL_POOL", "anthropic:claude-sonnet-5")
    asyncio.run(ensure_task_ledger(_manuscript(), _readers()[:1]))
    asyncio.run(update_task("m-phase3", "r1", 1, "running", increment_attempt=True))
    asyncio.run(update_task("m-phase3", "r1", 1, "failed", error="temporary provider error"))
    rows = asyncio.run(ensure_task_ledger(_manuscript(), _readers()[:1]))
    failed = next(row for row in rows if row["section_number"] == 1)
    assert failed["status"] == "failed"
    assert failed["attempts"] == 1
    assert "temporary" in failed["last_error"]


def test_usage_summary_separates_roles_and_marks_unknown_cost():
    summary = summarize_usage([
        {"role": "reader", "input_tokens": 100, "output_tokens": 50, "estimated_cost_usd": 0.01},
        {"role": "editor", "input_tokens": 200, "output_tokens": 75, "estimated_cost_usd": None},
    ])
    assert summary["calls"] == 2
    assert summary["input_tokens"] == 300
    assert summary["estimated_cost_usd"] == 0.01
    assert summary["has_unknown_cost"]
    assert summary["by_role"]["editor"]["calls"] == 1


def test_workflow_status_uses_task_completion_not_raw_counts(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "READER_MODEL_POOL", "anthropic:claude-sonnet-5")
    status = asyncio.run(workflow_status(_manuscript(), _readers()[:1]))
    assert status["total_tasks"] == 2
    assert status["completed_tasks"] == 0
    assert not status["complete"]
    assert task_id("m-phase3", "r1", 1).startswith("read-")
