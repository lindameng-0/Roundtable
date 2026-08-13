"""Editor V3: manuscript-aware synthesis with evidence-backed findings."""
import logging
import re
from typing import Any, Dict, List

import config as _cfg
from services.editor_evidence import aggregate_editor_evidence, evidence_json, manuscript_for_editor
from services.llm_gateway import structured_completion
from services.model_routing import route_for_role

logger = logging.getLogger(__name__)

EDITOR_TEMPERATURE = 0.2
FINDING_CLASSES = {
    "confirmed_contradiction",
    "likely_inconsistency",
    "reader_confusion",
    "ambiguity_or_insufficient_evidence",
}
PRIORITIES = {"critical", "important", "optional"}


def _evidence_ref(value: Any) -> Dict:
    value = value if isinstance(value, dict) else {}
    section = value.get("section")
    try:
        section = int(section) if section is not None else None
    except (TypeError, ValueError):
        section = None
    return {
        "section": section,
        "paragraph_id": str(value.get("paragraph_id") or "") or None,
        "reader": str(value.get("reader") or "") or None,
        "evidence_id": str(value.get("evidence_id") or "") or None,
        "note": str(value.get("note") or "")[:500],
    }


def _refs(value: Any) -> List[Dict]:
    return [_evidence_ref(item) for item in value if isinstance(item, dict)][:8] if isinstance(value, list) else []


_INLINE_CITATION = re.compile(
    r"\s*\[(?=[^\]\n]*(?:\bp-\d{6}\b|\bjournal\b|\bevidence\b))[^\]\n]{1,500}\]",
    re.IGNORECASE,
)


def _clean_prose(value: Any) -> str:
    """Remove model-authored citation shorthand; evidence lives in its own field."""
    text = _INLINE_CITATION.sub("", str(value or ""))
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r" +([,.;:!?])", r"\1", text).strip()


def _string(value: Any, limit: int = 4000) -> str:
    return _clean_prose(value)[:limit]


def _list(value: Any, limit: int = 20) -> List:
    return value[:limit] if isinstance(value, list) else []


def _default_editor_report(section_numbers: List[int]) -> Dict[str, Any]:
    return {
        "schema_version": 3,
        "executive_summary": {
            "synopsis": "",
            "overall_reader_experience": "",
            "strongest_asset": "",
            "main_friction": "",
            "top_priorities": [],
        },
        "reader_response": {
            "what_worked": [],
            "friction_points": [],
            "emotional_peaks": [],
            "meaningful_disagreements": [],
        },
        "story_integrity": [],
        "characters": [],
        "pacing_and_structure": [
            {"section": section, "engagement": "unknown", "diagnosis": "", "evidence": []}
            for section in section_numbers
        ],
        "revision_plan": [],
        "copy_edit_appendix": None,
        "coverage": {"sections": section_numbers, "partial": False, "notes": ""},
    }


def _normalize_editor_report(parsed: Dict, section_numbers: List[int]) -> Dict[str, Any]:
    default = _default_editor_report(section_numbers)
    parsed = parsed if isinstance(parsed, dict) else {}
    executive = parsed.get("executive_summary") if isinstance(parsed.get("executive_summary"), dict) else {}
    response = parsed.get("reader_response") if isinstance(parsed.get("reader_response"), dict) else {}
    coverage = parsed.get("coverage") if isinstance(parsed.get("coverage"), dict) else {}

    def evidence_items(value):
        result = []
        for item in _list(value):
            if not isinstance(item, dict):
                continue
            result.append({
                "title": _string(item.get("title"), 300),
                "analysis": _string(item.get("analysis")),
                "evidence": _refs(item.get("evidence")),
            })
        return result

    integrity = []
    for item in _list(parsed.get("story_integrity")):
        if not isinstance(item, dict):
            continue
        classification = item.get("classification")
        if classification not in FINDING_CLASSES:
            classification = "ambiguity_or_insufficient_evidence"
        confidence = item.get("confidence")
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.5
        integrity.append({
            "classification": classification,
            "title": _string(item.get("title"), 300),
            "explanation": _string(item.get("explanation")),
            "confidence": confidence,
            "severity": item.get("severity") if item.get("severity") in {"high", "medium", "low"} else "low",
            "evidence": _refs(item.get("evidence")),
        })

    characters = []
    for item in _list(parsed.get("characters")):
        if isinstance(item, dict) and _string(item.get("name")):
            characters.append({
                "name": _string(item.get("name"), 200),
                "reader_perception": _string(item.get("reader_perception")),
                "motivation_and_consistency": _string(item.get("motivation_and_consistency")),
                "relationship_notes": _string(item.get("relationship_notes")),
                "evidence": _refs(item.get("evidence")),
            })

    pacing = []
    for item in _list(parsed.get("pacing_and_structure"), 100):
        if not isinstance(item, dict):
            continue
        try:
            section = int(item.get("section"))
        except (TypeError, ValueError):
            continue
        pacing.append({
            "section": section,
            "engagement": item.get("engagement") if item.get("engagement") in {"high", "medium", "low", "mixed"} else "mixed",
            "diagnosis": _string(item.get("diagnosis")),
            "evidence": _refs(item.get("evidence")),
        })

    revisions = []
    for item in _list(parsed.get("revision_plan")):
        if not isinstance(item, dict):
            continue
        priority = item.get("priority") if item.get("priority") in PRIORITIES else "important"
        revisions.append({
            "priority": priority,
            "action": _string(item.get("action")),
            "reason": _string(item.get("reason")),
            "expected_impact": _string(item.get("expected_impact")),
            "evidence": _refs(item.get("evidence")),
        })

    return {
        "schema_version": 3,
        "executive_summary": {
            "synopsis": _string(executive.get("synopsis"), 6000),
            "overall_reader_experience": _string(executive.get("overall_reader_experience")),
            "strongest_asset": _string(executive.get("strongest_asset")),
            "main_friction": _string(executive.get("main_friction")),
            "top_priorities": [_string(item, 600) for item in _list(executive.get("top_priorities"), 5) if _string(item)],
        },
        "reader_response": {
            "what_worked": evidence_items(response.get("what_worked")),
            "friction_points": evidence_items(response.get("friction_points")),
            "emotional_peaks": evidence_items(response.get("emotional_peaks")),
            "meaningful_disagreements": evidence_items(response.get("meaningful_disagreements")),
        },
        "story_integrity": integrity,
        "characters": characters,
        "pacing_and_structure": pacing or default["pacing_and_structure"],
        "revision_plan": revisions,
        "copy_edit_appendix": parsed.get("copy_edit_appendix") if isinstance(parsed.get("copy_edit_appendix"), dict) else None,
        "coverage": {
            "sections": section_numbers,
            "partial": bool(coverage.get("partial")),
            "notes": _string(coverage.get("notes"), 1000),
        },
    }


def validate_editor_report(report: Dict) -> List[str]:
    errors = []
    executive = report.get("executive_summary") or {}
    for key in ("synopsis", "overall_reader_experience", "strongest_asset", "main_friction"):
        if not _string(executive.get(key)):
            errors.append(f"executive_summary.{key} is required")
    if not executive.get("top_priorities"):
        errors.append("executive_summary.top_priorities is required")
    if not report.get("revision_plan"):
        errors.append("revision_plan is required")
    return errors


def _ground_report_evidence(report: Dict, manuscript: Dict, aggregate: Dict) -> None:
    """Drop invented references and enrich valid reaction references in place."""
    paragraph_ids = {
        paragraph.get("paragraph_id")
        for section in manuscript.get("sections") or []
        for paragraph in section.get("paragraph_lines") or []
        if paragraph.get("paragraph_id")
    }
    evidence_by_id = {
        item["evidence_id"]: item
        for item in aggregate.get("evidence") or []
        if item.get("evidence_id")
    }

    def clean_refs(container: Dict) -> None:
        grounded = []
        for ref in container.get("evidence") or []:
            evidence_id = ref.get("evidence_id")
            paragraph_id = ref.get("paragraph_id")
            source = evidence_by_id.get(evidence_id)
            if source:
                grounded.append({
                    "section": source.get("section"),
                    "paragraph_id": source.get("paragraph_id"),
                    "reader": source.get("reader"),
                    "evidence_id": evidence_id,
                    "note": ref.get("note") or source.get("comment", ""),
                })
            elif paragraph_id in paragraph_ids:
                grounded.append({**ref, "evidence_id": None})
            elif ref.get("section") in {s.get("section_number") for s in manuscript.get("sections") or []}:
                grounded.append({**ref, "paragraph_id": None, "evidence_id": None})
        container["evidence"] = grounded[:8]

    response = report.get("reader_response") or {}
    for group in response.values():
        for item in group if isinstance(group, list) else []:
            clean_refs(item)
    for key in ("story_integrity", "characters", "pacing_and_structure", "revision_plan"):
        for item in report.get(key) or []:
            clean_refs(item)


def _editor_system_prompt(genre: str) -> str:
    return f"""You are Editor V3, synthesizing a {genre or 'fiction'} manuscript and independent beta-reader evidence.

You have the manuscript itself, so write a genuine synopsis and inspect continuity directly. Reader feedback tells you what affected the reading experience; it is evidence, not ground truth.

INTEGRITY RULES:
- Never call confusion a plot hole by itself.
- Classify each integrity finding as exactly one of: confirmed_contradiction, likely_inconsistency, reader_confusion, ambiguity_or_insufficient_evidence.
- confirmed_contradiction requires two incompatible manuscript facts with paragraph evidence.
- likely_inconsistency requires strong but incomplete evidence.
- If ambiguity may be deliberate, use ambiguity_or_insufficient_evidence.
- Include zero integrity findings if none are justified.
- Every material claim and every revision recommendation needs evidence references using section, paragraph_id, reader, or evidence_id from the supplied data.
- Put citations only in each item's structured evidence array. Never write bracketed citations, paragraph IDs, reader-journal labels, or source lists inside prose fields.
- Separate reader taste from objective story logic.
- Use question_lifecycle to distinguish successfully paid-off questions from still-open confusion. A resolved
  question may be a strength, unless its history shows the reader remained unproductively confused too long.
- Do not give generic advice. State the concrete change and expected reader impact.

Return JSON only with this exact top-level shape:
{{
 "schema_version": 3,
 "executive_summary": {{
   "synopsis": "complete spoiler-aware story summary",
   "overall_reader_experience": "balanced synthesis",
   "strongest_asset": "single most important strength",
   "main_friction": "single most important problem or 'No dominant friction identified'",
   "top_priorities": ["3-5 ordered revision priorities"]
 }},
 "reader_response": {{
   "what_worked": [{{"title":"...","analysis":"...","evidence":[{{"section":1,"paragraph_id":"p-000001","reader":"Name","evidence_id":"...","note":"..."}}]}}],
   "friction_points": [same item shape],
   "emotional_peaks": [same item shape],
   "meaningful_disagreements": [same item shape]
 }},
 "story_integrity": [{{"classification":"confirmed_contradiction|likely_inconsistency|reader_confusion|ambiguity_or_insufficient_evidence","title":"...","explanation":"...","confidence":0.0,"severity":"high|medium|low","evidence":[]}}],
 "characters": [{{"name":"...","reader_perception":"...","motivation_and_consistency":"...","relationship_notes":"...","evidence":[]}}],
 "pacing_and_structure": [{{"section":1,"engagement":"high|medium|low|mixed","diagnosis":"...","evidence":[]}}],
 "revision_plan": [{{"priority":"critical|important|optional","action":"specific revision","reason":"...","expected_impact":"...","evidence":[]}}],
 "coverage": {{"partial":false,"notes":"..."}}
}}"""


async def generate_editor_report(manuscript: Dict, reactions: List[Dict]) -> Dict:
    evidence = aggregate_editor_evidence(reactions)
    section_numbers = [row["section"] for row in evidence["sections"]]
    if _cfg.MOCK_LLM:
        report = _default_editor_report(section_numbers)
        report["executive_summary"] = {
            "synopsis": "Mock synopsis for local interface testing.",
            "overall_reader_experience": "Mock readers completed the available sections.",
            "strongest_asset": "Local workflow coverage.",
            "main_friction": "Live literary judgment is unavailable in mock mode.",
            "top_priorities": ["Run with a live editor model for substantive analysis."],
        }
        report["revision_plan"] = [{
            "priority": "important", "action": "Enable a live editor model.",
            "reason": "Mock mode does not analyze prose.", "expected_impact": "Produces a real report.", "evidence": [],
        }]
        return report

    manuscript_text, manuscript_truncated = manuscript_for_editor(manuscript)
    evidence_text, evidence_truncated = evidence_json(evidence)
    user_message = (
        "MANUSCRIPT WITH STABLE PARAGRAPH IDS:\n" + manuscript_text +
        "\n\nDETERMINISTIC READER EVIDENCE:\n" + evidence_text +
        "\n\nGenerate the complete Editor V3 report."
    )
    route = route_for_role("editor")
    completion = await structured_completion(
        route=route, role="editor", system_prompt=_editor_system_prompt(manuscript.get("genre", "fiction")),
        user_prompt=user_message, temperature=EDITOR_TEMPERATURE, max_tokens=12000,
    )
    report = _normalize_editor_report(completion.data, section_numbers)
    _ground_report_evidence(report, manuscript, evidence)
    report["coverage"]["partial"] = bool(manuscript_truncated or evidence_truncated)
    if report["coverage"]["partial"] and not report["coverage"]["notes"]:
        report["coverage"]["notes"] = "The manuscript or reader-evidence input was truncated to the editor budget."
    errors = validate_editor_report(report)
    if errors:
        raise RuntimeError("Editor V3 returned an incomplete report: " + "; ".join(errors))
    report["_generation"] = {
        "provider": route.provider, "model": route.model, "usage": completion.usage.to_dict(),
    }
    return report


async def generate_copy_edit_appendix(manuscript: Dict) -> Dict:
    manuscript_text, truncated = manuscript_for_editor(manuscript, max_chars=160_000)
    route = route_for_role("copyedit")
    system = """You are a conservative copy editor. Find only high-confidence mechanical issues: typos, missing or repeated words, incorrect word use, broken sentences, punctuation that changes meaning, and accidental tense or viewpoint shifts. Do not rewrite style, remove voice, enforce preferences, or report uncertain issues. Return JSON: {"summary":"...","items":[{"paragraph_id":"p-000001","category":"typo|word_usage|missing_or_repeated_word|broken_sentence|punctuation|tense_or_viewpoint","original":"short excerpt","suggestion":"minimal correction","explanation":"...","confidence":0.0}]}."""
    completion = await structured_completion(
        route=route, role="copyedit", system_prompt=system,
        user_prompt="MANUSCRIPT:\n" + manuscript_text, temperature=0.0, max_tokens=6000,
    )
    raw = completion.data if isinstance(completion.data, dict) else {}
    items = []
    allowed = {"typo", "word_usage", "missing_or_repeated_word", "broken_sentence", "punctuation", "tense_or_viewpoint"}
    for item in _list(raw.get("items"), 250):
        if not isinstance(item, dict) or item.get("category") not in allowed:
            continue
        try:
            confidence = float(item.get("confidence", 0))
        except (TypeError, ValueError):
            confidence = 0
        if confidence < 0.75:
            continue
        items.append({
            "paragraph_id": _string(item.get("paragraph_id"), 40),
            "category": item["category"],
            "original": _string(item.get("original"), 300),
            "suggestion": _string(item.get("suggestion"), 300),
            "explanation": _string(item.get("explanation"), 600),
            "confidence": round(min(1.0, confidence), 2),
        })
    return {
        "summary": _string(raw.get("summary"), 1200), "items": items, "partial": truncated,
        "_generation": {"provider": route.provider, "model": route.model, "usage": completion.usage.to_dict()},
    }
