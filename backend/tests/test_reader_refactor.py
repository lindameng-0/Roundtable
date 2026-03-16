"""Quick sanity tests for reader pipeline refactor (new schema, parsing, memory)."""
import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import parse_reader_response, validate_moments, VALID_MOMENT_TYPES


def test_parse_new_schema():
    sample = json.dumps({
        "checking_in": "Curious.",
        "reading_journal": "I liked it.",
        "what_i_think_the_writer_is_doing": "Setup.",
        "moments": [{"paragraph": 1, "type": "reaction", "comment": "Nice."}],
        "questions_for_writer": [],
        "memory_update": {"facts": "X happened.", "impressions": "", "watching_for": "", "feeling": "engaged"},
    })
    parsed = parse_reader_response(sample)
    assert parsed.get("checking_in") == "Curious."
    assert parsed.get("reading_journal") == "I liked it."
    assert len(parsed.get("moments")) == 1
    assert parsed["moments"][0]["type"] == "reaction"
    assert parsed.get("questions_for_writer") == []
    assert "facts" in parsed.get("memory_update", {})


def test_parse_strips_fences():
    raw = '```json\n{"moments": [], "reading_journal": "x", "checking_in": null, "what_i_think_the_writer_is_doing": null, "questions_for_writer": [], "memory_update": {}}\n```'
    parsed = parse_reader_response(raw)
    assert "moments" in parsed
    assert parsed.get("reading_journal") == "x"


def test_validate_moments():
    moments = [{"paragraph": 5, "type": "craft", "comment": "Good line."}, {"paragraph": 100, "type": "reaction", "comment": "x"}]
    valid = validate_moments(moments, line_start=1, line_end=50)
    assert len(valid) == 2
    assert valid[0]["paragraph"] == 5 and valid[0]["type"] == "craft"
    assert valid[1]["paragraph"] == 50  # clamped


if __name__ == "__main__":
    test_parse_new_schema()
    test_parse_strips_fences()
    test_validate_moments()
    print("All refactor tests passed.")
