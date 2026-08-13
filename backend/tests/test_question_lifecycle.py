from services.editor_evidence import aggregate_editor_evidence
from services.reader_contract import validate_reader_output
from services.reader_questions import active_questions, question_id, question_ledger


PARAGRAPHS = [
    {"line": 10, "paragraph_id": "p-000010", "text": "The hidden letter was addressed to Mara."},
]


def test_question_ids_are_stable_per_reader_section_and_text():
    assert question_id("r1", 1, "Who sent it?") == question_id("r1", 1, "  who   sent it? ")
    assert question_id("r1", 1, "Who sent it?") != question_id("r2", 1, "Who sent it?")


def test_reader_output_creates_question_events_and_validates_updates():
    qid = question_id("r1", 1, "Who sent the letter?")
    output, warnings = validate_reader_output({
        "reading_journal": "The address answers my earlier question.",
        "questions_for_writer": ["Why did Mara hide it?"],
        "question_kinds": ["story_question"],
        "question_updates": [
            {"question_id": qid, "status": "resolved", "resolution": "It was sent to Mara.", "paragraph_id": "p-000010"},
            {"question_id": "q-someone-else", "status": "resolved", "resolution": "Invalid.", "paragraph_id": "p-000010"},
        ],
    }, PARAGRAPHS, open_questions=[{
        "question_id": qid, "question": "Who sent the letter?", "status": "open",
    }], reader_id="r1", section_number=2)
    assert output["question_events"][0]["raised_section"] == 2
    assert output["question_updates"] == [{
        "question_id": qid, "status": "resolved", "resolution": "It was sent to Mara.",
        "paragraph_id": "p-000010", "section": 2,
    }]
    assert warnings


def test_ledger_preserves_original_question_and_resolution_history():
    qid = question_id("r1", 1, "Who sent the letter?")
    reactions = [
        {"reader_id": "r1", "reader_name": "Aisha", "section_number": 1, "response_json": {
            "question_events": [{"question_id": qid, "question": "Who sent the letter?", "kind": "story_question", "raised_section": 1}],
            "questions_for_writer": ["Who sent the letter?"],
        }},
        {"reader_id": "r1", "reader_name": "Aisha", "section_number": 2, "response_json": {
            "question_updates": [{"question_id": qid, "status": "resolved", "resolution": "The address shows it was meant for Mara.", "paragraph_id": "p-000010"}],
        }},
    ]
    ledger = question_ledger(reactions, "r1")
    assert ledger[0]["question"] == "Who sent the letter?"
    assert ledger[0]["status"] == "resolved"
    assert len(ledger[0]["history"]) == 2
    assert active_questions(ledger) == []


def test_editor_evidence_separates_resolved_from_open_questions():
    qid = question_id("r1", 1, "Who sent the letter?")
    evidence = aggregate_editor_evidence([
        {"reader_id": "r1", "reader_name": "Aisha", "section_number": 1, "response_json": {
            "question_events": [{"question_id": qid, "question": "Who sent the letter?", "kind": "story_question", "raised_section": 1}],
            "questions_for_writer": ["Who sent the letter?"],
        }},
        {"reader_id": "r1", "reader_name": "Aisha", "section_number": 2, "response_json": {
            "question_updates": [{"question_id": qid, "status": "resolved", "resolution": "It was addressed to Mara.", "paragraph_id": "p-000010"}],
        }},
    ])
    assert len(evidence["resolved_questions"]) == 1
    assert evidence["open_questions"] == []
    assert evidence["repeated_questions"] == []
