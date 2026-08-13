import asyncio
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-key")
os.environ.setdefault("GEMINI_API_KEY", "test-key")

from routers import api
from services.editor import _default_editor_report
from services.manuscript import split_manuscript
from services.reader_memory import latest_memory, normalize_memory_update


class _HeadersRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


class _ManuscriptTable:
    def __init__(self, manuscript):
        self.manuscript = manuscript

    async def find_one(self, *_args, **_kwargs):
        return self.manuscript


class _Db:
    def __init__(self, manuscript):
        self.manuscripts = _ManuscriptTable(manuscript)


def test_sections_receive_stable_paragraph_ids():
    text = "Chapter One\n\nFirst paragraph.\n\nSecond paragraph."
    first, _ = split_manuscript(text)
    second, _ = split_manuscript(text)
    first_ids = [p["paragraph_id"] for s in first for p in s["paragraph_lines"]]
    second_ids = [p["paragraph_id"] for s in second for p in s["paragraph_lines"]]
    assert first_ids == second_ids
    assert len(first_ids) == len(set(first_ids))
    assert all(value.startswith("p-") for value in first_ids)


def test_memory_module_preserves_existing_rolling_behavior():
    memories = [{"memory_json": {"facts": "A", "impressions": "B", "watching_for": "C", "feeling": "D"}}]
    assert latest_memory(memories)["watching_for"] == "C"
    assert normalize_memory_update({"facts": " x ", "feeling": " y "}) == {
        "facts": "x", "impressions": "", "watching_for": "", "feeling": "y"
    }


def test_editor_report_has_versioned_canonical_contract():
    report = _default_editor_report([1, 2])
    assert report["schema_version"] == 3
    assert {"executive_summary", "reader_response", "story_integrity", "revision_plan"}.issubset(report)


def test_selected_reader_resume_checks_ids_not_counts():
    reactions = [{"reader_id": "other-1"}, {"reader_id": "other-2"}]
    assert not api._selected_readers_complete(reactions, [{"id": "selected"}])
    assert api._selected_readers_complete(reactions + [{"reader_id": "selected"}], [{"id": "selected"}])


def test_guest_manuscript_requires_matching_capability(monkeypatch):
    token = "guest-secret"
    monkeypatch.setattr(api, "db", _Db({
        "id": "m1", "user_id": None, "access_token_hash": api._hash_manuscript_token(token)
    }))
    manuscript = asyncio.run(api._get_owned_manuscript("m1", _HeadersRequest({"x-manuscript-token": token})))
    assert manuscript["id"] == "m1"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._get_owned_manuscript("m1", _HeadersRequest()))
    assert exc.value.status_code == 403


def test_authenticated_manuscript_requires_owner(monkeypatch):
    monkeypatch.setattr(api, "db", _Db({"id": "m1", "user_id": "owner"}))

    async def wrong_user(_request):
        return {"user_id": "someone-else"}

    monkeypatch.setattr(api, "_get_optional_user", wrong_user)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api._get_owned_manuscript("m1", _HeadersRequest()))
    assert exc.value.status_code == 403
