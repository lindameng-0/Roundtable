import asyncio

import config
from services.model_routing import fallback_routes_for_reader, parse_route, route_for_reader, usage_record
from services.reader_prompts_v2 import build_reader_v2_prompts
from services.reader_contract import merge_state, state_for_prompt, validate_reader_output
from services.reader_profiles import behavioral_profile, profile_prompt
from services.reader_v2 import get_reader_reaction_v2


PARAGRAPHS = [
    {"line": 1, "paragraph_id": "p-000001", "text": "Mara left the key beneath the blue cup."},
    {"line": 2, "paragraph_id": "p-000002", "text": "At midnight, the cup was gone."},
]


def test_routes_rotate_across_readers(monkeypatch):
    monkeypatch.setattr(
        config,
        "READER_MODEL_POOL",
        "gemini:gemini-2.5-flash,anthropic:claude-sonnet-5,openai:gpt-5.6-luna",
    )
    assert route_for_reader({"avatar_index": 0}).provider == "gemini"
    assert route_for_reader({"avatar_index": 1}).provider == "anthropic"
    assert route_for_reader({"avatar_index": 2}).provider == "openai"
    assert parse_route("openai:gpt-5.6-terra").model == "gpt-5.6-terra"
    assert [route.provider for route in fallback_routes_for_reader({"avatar_index": 1})] == [
        "anthropic", "gemini", "openai"
    ]


def test_usage_cost_is_explicit_and_unknown_is_none():
    known = usage_record(parse_route("gemini:gemini-2.5-flash"), "reader", 1000, 500)
    assert known.estimated_cost_usd == 0.00155
    unknown = usage_record(parse_route("openai:future-model"), "reader", 10, 10)
    assert unknown.estimated_cost_usd is None


def test_profiles_are_biases_not_forced_personality():
    profile = behavioral_profile({"name": "Mina", "avatar_index": 3, "reading_habits": "Reads on weekends."})
    assert profile["attention"] == "emotion"
    prompt = profile_prompt({"name": "Mina", "avatar_index": 3})
    assert "mild attention bias" in prompt
    assert "never force" in prompt


def test_v2_prompt_requests_candid_friction_without_forcing_faults():
    system, _ = build_reader_v2_prompts(
        {"name": "Mina", "avatar_index": 0}, "fiction", 1, 1, PARAGRAPHS, {}
    )
    assert "Be candid about friction" in system
    assert "do not invent a criticism" in system
    assert 'avoid workshop questions such as "is this meant to...?"' in system


def test_contract_rejects_fabricated_paragraph_and_bounds_state():
    output, warnings = validate_reader_output(
        {
            "reading_journal": "I expected the key to matter, and the missing cup made me suspicious.",
            "moments": [
                {"paragraph_id": "p-000002", "type": "reaction", "comment": "Now I distrust whoever entered."},
                {"paragraph_id": "p-999999", "type": "craft", "comment": "Not in the text."},
            ],
            "questions_for_writer": ["Who moved it?", "Did Mara see them?", "Too many"],
            "state_delta": {"facts": ["The blue cup disappeared."]},
        },
        PARAGRAPHS,
    )
    assert len(output["moments"]) == 1
    assert output["moments"][0]["paragraph"] == 2
    assert len(output["questions_for_writer"]) == 2
    assert warnings


def test_state_delta_preserves_continuity_without_transcript_growth():
    previous = {
        "facts": [f"fact {i}" for i in range(8)],
        "impressions": ["Mara is cautious."],
        "open_threads": ["Who has the key?"],
        "emotional_state": ["curious"],
    }
    merged = merge_state(previous, {
        "facts": ["The cup disappeared."],
        "open_threads": ["Who moved the cup?"],
        "emotional_state": ["uneasy"],
    })
    assert len(merged["facts"]) == 8
    assert merged["facts"][-1] == "The cup disappeared."
    assert merged["emotional_state"] == ["uneasy"]
    assert "Who moved the cup?" in state_for_prompt(merged)


def test_v2_mock_pipeline_persists_reaction_state_and_usage(monkeypatch):
    config.db.clear()
    monkeypatch.setattr(config, "MOCK_LLM", True)
    monkeypatch.setattr(config, "READER_MODEL_POOL", "gemini:gemini-2.5-flash")
    reader = {"id": "r1", "name": "Mina", "avatar_index": 0, "reading_habits": "Reads fiction."}
    section = {"section_number": 1, "total_sections": 2, "paragraph_lines": PARAGRAPHS}

    result = asyncio.run(get_reader_reaction_v2(reader, section, "mystery", "m1"))

    assert result["model"]["model"] == "gemini-2.5-flash"
    assert result["usage"]["input_tokens"] > 0
    reaction = asyncio.run(config.db.reader_reactions.find_one({"reader_id": "r1"}))
    memory = asyncio.run(config.db.reader_memories.find_one({"reader_id": "r1"}))
    assert reaction["response_json"]["pipeline_version"] == "v2"
    assert memory["memory_json"]["schema_version"] == 2
