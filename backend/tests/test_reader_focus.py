import asyncio

from fastapi.testclient import TestClient

import config
from server import app
from services.reader_focus import FOCUS_LABELS, focus_prompt


def _reader():
    return {
        "id": "reader-focus-1", "manuscript_id": "manuscript-focus-1",
        "name": "Mara Ellison", "age": 34, "occupation": "bookseller",
        "personality": "skeptical", "reading_habits": "Reads historical fiction weekly.",
        "liked_tropes": ["forbidden love across enemy lines", "reluctant collaborators"],
        "disliked_tropes": ["historical characters behaving with unexplained modern certainty"],
        "voice_style": "plainspoken", "temperature": 0.6, "quote": "Make me believe it.",
        "avatar_index": 0, "created_at": "2026-01-01T00:00:00+00:00",
        "primary_focus": None, "secondary_focuses": [], "writer_focus_note": "",
    }


def _seed(locked=False):
    async def scenario():
        config.db.clear()
        await config.db.manuscripts.insert_one({
            "id": "manuscript-focus-1", "title": "Test", "raw_text": "Text",
            "sections": [], "reader_config_locked": locked, "created_at": "2026-01-01T00:00:00+00:00",
        })
        await config.db.reader_personas.insert_one(_reader())
    asyncio.run(scenario())


def test_focus_catalog_is_bounded_and_grouped():
    assert 16 <= len(FOCUS_LABELS) <= 24
    assert "relationship_chemistry" in FOCUS_LABELS
    assert "plot_logic" in FOCUS_LABELS


def test_prompt_keeps_tastes_and_assignment_soft():
    reader = {
        **_reader(), "primary_focus": "relationship_chemistry",
        "secondary_focuses": ["plot_logic"],
        "writer_focus_note": "Watch whether the romance feels earned.",
    }
    prompt = focus_prompt(reader)
    assert "forbidden love across enemy lines" in prompt
    assert "not conclusions" in prompt
    assert "not what opinion you must reach" in prompt
    assert "Do not force" in prompt
    assert "romance feels earned" in prompt


def test_writer_can_assign_focus_and_dismiss_generated_taste():
    _seed()
    with TestClient(app) as client:
        response = client.patch(
            "/api/manuscripts/manuscript-focus-1/personas/reader-focus-1/focus",
            json={
                "primary_focus": "relationship_chemistry",
                "secondary_focuses": ["plot_logic", "dialogue"],
                "writer_focus_note": "Watch whether the romance feels earned.",
                "liked_tropes": ["forbidden love across enemy lines"],
                "disliked_tropes": [],
            },
        )
    assert response.status_code == 200, response.text
    assert response.json()["primary_focus"] == "relationship_chemistry"
    assert response.json()["liked_tropes"] == ["forbidden love across enemy lines"]


def test_focus_cannot_change_after_run_is_locked():
    _seed(locked=True)
    with TestClient(app) as client:
        response = client.patch(
            "/api/manuscripts/manuscript-focus-1/personas/reader-focus-1/focus",
            json={
                "primary_focus": "plot_logic", "secondary_focuses": [], "writer_focus_note": "",
                "liked_tropes": _reader()["liked_tropes"],
                "disliked_tropes": _reader()["disliked_tropes"],
            },
        )
    assert response.status_code == 409
    assert "locked" in response.json()["detail"].lower()
