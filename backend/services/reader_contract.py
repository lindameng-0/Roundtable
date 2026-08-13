"""Reader V2 response validation and bounded state merging."""
from typing import Any, Dict, List, Tuple

from services.reader_questions import QUESTION_KINDS, question_id


MOMENT_TYPES = {"reaction", "confusion", "question", "craft", "callback"}
STATE_KEYS = ("facts", "impressions", "open_threads", "emotional_state")
STATE_LIMITS = {"facts": 8, "impressions": 6, "open_threads": 5, "emotional_state": 1}


def _clean_text(value: Any, limit: int = 500) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _clean_list(value: Any, item_limit: int = 240) -> List[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _clean_text(item, item_limit)
        if text and text not in result:
            result.append(text)
    return result


def empty_state() -> Dict[str, List[str]]:
    return {key: [] for key in STATE_KEYS}


def normalize_state(value: Any) -> Dict[str, List[str]]:
    state = empty_state()
    if not isinstance(value, dict):
        return state
    for key in STATE_KEYS:
        raw = value.get(key)
        if isinstance(raw, str):
            raw = [raw]
        state[key] = _clean_list(raw)[: STATE_LIMITS[key]]
    return state


def merge_state(previous: Any, delta: Any) -> Dict[str, List[str]]:
    """Apply explicit additions/removals, retaining only useful recent state."""
    state = normalize_state(previous)
    if not isinstance(delta, dict):
        return state
    for key in STATE_KEYS:
        additions = _clean_list(delta.get(key))
        removals = {item.lower() for item in _clean_list(delta.get(f"resolved_{key}"))}
        kept = [item for item in state[key] if item.lower() not in removals]
        for item in additions:
            if item.lower() not in {existing.lower() for existing in kept}:
                kept.append(item)
        state[key] = kept[-STATE_LIMITS[key] :]
    return state


def state_for_prompt(state: Any) -> str:
    normalized = normalize_state(state)
    if not any(normalized.values()):
        return "No previous sections read."
    labels = {
        "facts": "Events remembered",
        "impressions": "Current impressions",
        "open_threads": "Questions or expectations still open",
        "emotional_state": "Current feeling",
    }
    lines = []
    for key in STATE_KEYS:
        if normalized[key]:
            lines.append(f"{labels[key]}: " + " | ".join(normalized[key]))
    return "\n".join(lines)


def validate_reader_output(
    raw: Any,
    paragraphs: List[Dict],
    *,
    open_questions: List[Dict] | None = None,
    reader_id: str = "reader",
    section_number: int = 0,
) -> Tuple[Dict, List[str]]:
    warnings: List[str] = []
    data = raw if isinstance(raw, dict) else {}
    by_line = {int(p["line"]): p for p in paragraphs if p.get("line") is not None}
    by_id = {p.get("paragraph_id"): p for p in paragraphs if p.get("paragraph_id")}
    moments = []
    for item in data.get("moments", []) if isinstance(data.get("moments"), list) else []:
        if not isinstance(item, dict):
            continue
        paragraph = by_id.get(item.get("paragraph_id"))
        if paragraph is None:
            try:
                paragraph = by_line.get(int(item.get("paragraph")))
            except (TypeError, ValueError):
                paragraph = None
        if paragraph is None:
            warnings.append("moment referenced a paragraph outside this section")
            continue
        comment = _clean_text(item.get("comment"), 600)
        if not comment:
            continue
        moment_type = item.get("type") if item.get("type") in MOMENT_TYPES else "reaction"
        moments.append({
            "paragraph": int(paragraph["line"]),
            "paragraph_id": paragraph.get("paragraph_id") or f"p-{int(paragraph['line']):06d}",
            "type": moment_type,
            "comment": comment,
        })

    questions = _clean_list(data.get("questions_for_writer"), 400)[:2]
    question_kinds = data.get("question_kinds") if isinstance(data.get("question_kinds"), list) else []
    question_events = []
    for index, question in enumerate(questions):
        kind = question_kinds[index] if index < len(question_kinds) and question_kinds[index] in QUESTION_KINDS else "story_question"
        question_events.append({
            "question_id": question_id(reader_id, section_number, question),
            "question": question,
            "kind": kind,
            "status": "open",
            "raised_section": section_number,
        })

    allowed_questions = {item.get("question_id"): item for item in (open_questions or []) if item.get("question_id")}
    question_updates = []
    for item in data.get("question_updates", []) if isinstance(data.get("question_updates"), list) else []:
        if not isinstance(item, dict) or item.get("question_id") not in allowed_questions:
            warnings.append("question update referenced an unknown or resolved question")
            continue
        status = item.get("status")
        if status not in {"partially_resolved", "resolved", "reinterpreted"}:
            continue
        resolution = _clean_text(item.get("resolution"), 800)
        paragraph = by_id.get(item.get("paragraph_id"))
        if not resolution or paragraph is None:
            warnings.append("question update lacked a valid explanation or current paragraph")
            continue
        question_updates.append({
            "question_id": item["question_id"],
            "status": status,
            "resolution": resolution,
            "paragraph_id": paragraph.get("paragraph_id"),
            "section": section_number,
        })
    journal = _clean_text(data.get("reading_journal"), 1800)
    if not journal:
        journal = "I don't have a clear reaction to this section yet."
        warnings.append("missing reading journal")
    output = {
        "checking_in": _clean_text(data.get("checking_in"), 500) or None,
        "reading_journal": journal,
        "what_i_think_the_writer_is_doing": _clean_text(
            data.get("what_i_think_the_writer_is_doing"), 600
        ) or None,
        "moments": moments[:6],
        "questions_for_writer": questions,
        "question_events": question_events,
        "question_updates": question_updates[:4],
        "state_delta": {
            key: _clean_list((data.get("state_delta") or {}).get(key), 240)
            for key in STATE_KEYS
        } if isinstance(data.get("state_delta"), dict) else empty_state(),
    }
    return output, warnings
