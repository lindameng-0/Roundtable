from services.editor import _clean_prose, _ground_report_evidence, _normalize_editor_report, validate_editor_report
import json

from services.editor_evidence import aggregate_editor_evidence, dedupe_reactions, evidence_json, manuscript_for_editor


def _reaction(created_at="2026-01-01", comment="I stumbled here"):
    return {
        "reader_id": "reader-1",
        "reader_name": "Aisha",
        "section_number": 1,
        "created_at": created_at,
        "response_json": {
            "moments": [{"paragraph_id": "p-000001", "type": "confusion", "comment": comment}],
            "questions_for_writer": ["Is this intentional?"],
            "reading_journal": "Interested, but briefly confused.",
        },
    }


def test_editor_evidence_deduplicates_reader_section_retries():
    reactions = [_reaction("2026-01-01", "old"), _reaction("2026-01-02", "new")]
    clean = dedupe_reactions(reactions)
    aggregate = aggregate_editor_evidence(reactions)
    assert len(clean) == 1
    assert aggregate["reaction_count"] == 1
    assert aggregate["evidence"][0]["comment"] == "new"


def test_manuscript_editor_input_uses_stable_paragraph_ids():
    rendered, truncated = manuscript_for_editor({"sections": [{
        "section_number": 1,
        "paragraph_lines": [{"paragraph_id": "p-000001", "line": 1, "text": "Opening."}],
    }]})
    assert "[p-000001] Opening." in rendered
    assert not truncated


def test_v3_normalization_and_validation_require_substantive_report():
    report = _normalize_editor_report({"executive_summary": {"synopsis": "Only a synopsis"}}, [1])
    errors = validate_editor_report(report)
    assert "executive_summary.overall_reader_experience is required" in errors
    assert "revision_plan is required" in errors


def test_truncated_evidence_is_still_valid_json():
    aggregate = aggregate_editor_evidence([_reaction(comment="x" * 800)])
    rendered, truncated = evidence_json(aggregate, max_chars=200)
    assert truncated
    assert isinstance(json.loads(rendered), dict)


def test_internal_citation_shorthand_is_removed_from_prose():
    text = "The turn feels abrupt [Mara Ellison journal; p-000048-p-000051], but effective."
    assert _clean_prose(text) == "The turn feels abrupt, but effective."
    assert _clean_prose("The narrator says [perhaps] deliberately.") == "The narrator says [perhaps] deliberately."


def test_grounding_drops_invented_references_and_enriches_real_ones():
    manuscript = {"sections": [{"section_number": 1, "paragraph_lines": [
        {"paragraph_id": "p-000001", "text": "Opening."},
    ]}]}
    aggregate = aggregate_editor_evidence([_reaction()])
    report = {
        "reader_response": {"friction_points": [{"evidence": [
            {"evidence_id": "r-reader-1-s1-m1"},
            {"paragraph_id": "p-invented"},
        ]}]},
        "story_integrity": [], "characters": [], "pacing_and_structure": [], "revision_plan": [],
    }
    _ground_report_evidence(report, manuscript, aggregate)
    refs = report["reader_response"]["friction_points"][0]["evidence"]
    assert refs == [{
        "section": 1,
        "paragraph_id": "p-000001",
        "reader": "Aisha",
        "evidence_id": "r-reader-1-s1-m1",
        "note": "I stumbled here",
    }]
