"""Deterministic evidence preparation for Editor V3."""
import json
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from services.reader_questions import question_ledger


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def dedupe_reactions(reactions: List[Dict]) -> List[Dict]:
    """Keep one saved reaction per reader/section, preferring the newest row."""
    chosen = {}
    for reaction in reactions:
        key = (reaction.get("reader_id"), reaction.get("section_number"))
        current = chosen.get(key)
        if current is None or str(reaction.get("created_at", "")) >= str(current.get("created_at", "")):
            chosen[key] = reaction
    return sorted(chosen.values(), key=lambda item: (item.get("section_number") or 0, item.get("reader_name") or ""))


def aggregate_editor_evidence(reactions: List[Dict]) -> Dict:
    clean = dedupe_reactions(reactions)
    sections = defaultdict(lambda: {"readers": [], "moment_count": 0, "question_count": 0})
    evidence = []
    questions = defaultdict(lambda: {"question": "", "readers": set(), "sections": set()})
    paragraph_readers = defaultdict(set)

    for reaction in clean:
        response = reaction.get("response_json") or {}
        reader_id = reaction.get("reader_id") or "unknown"
        reader_name = reaction.get("reader_name") or "Reader"
        section = int(reaction.get("section_number") or 0)
        moments = response.get("moments") or reaction.get("inline_comments") or []
        section_entry = sections[section]
        section_entry["readers"].append({
            "reader_id": reader_id,
            "reader_name": reader_name,
            "checking_in": response.get("checking_in"),
            "journal": response.get("reading_journal") or reaction.get("section_reflection"),
            "intent_read": response.get("what_i_think_the_writer_is_doing"),
        })
        section_entry["moment_count"] += len(moments)
        for index, moment in enumerate(moments):
            paragraph_id = moment.get("paragraph_id")
            paragraph = moment.get("paragraph", moment.get("line"))
            if not paragraph_id and paragraph:
                paragraph_id = f"p-{int(paragraph):06d}"
            evidence_id = f"r-{reader_id}-s{section}-m{index + 1}"
            evidence.append({
                "evidence_id": evidence_id,
                "reader_id": reader_id,
                "reader": reader_name,
                "section": section,
                "paragraph_id": paragraph_id,
                "paragraph": paragraph,
                "type": moment.get("type", "reaction"),
                "comment": str(moment.get("comment") or "")[:800],
            })
            if paragraph_id:
                paragraph_readers[(section, paragraph_id)].add(reader_name)
        for question in response.get("questions_for_writer") or []:
            normalized = _norm(question)
            if not normalized:
                continue
            questions[normalized]["question"] = str(question).strip()
            questions[normalized]["readers"].add(reader_name)
            questions[normalized]["sections"].add(section)
            section_entry["question_count"] += 1

    consensus = [
        {"section": section, "paragraph_id": paragraph_id, "readers": sorted(readers), "reader_count": len(readers)}
        for (section, paragraph_id), readers in paragraph_readers.items()
        if len(readers) >= 2
    ]
    lifecycle = question_ledger(clean)
    open_normalized = {_norm(item["question"]) for item in lifecycle if item.get("status") != "resolved"}
    question_rows = [
        {
            "question": value["question"],
            "readers": sorted(value["readers"]),
            "sections": sorted(value["sections"]),
            "reader_count": len(value["readers"]),
        }
        for key, value in questions.items() if key in open_normalized
    ]
    return {
        "reaction_count": len(clean),
        "reader_count": len({item.get("reader_id") for item in clean}),
        "sections": [{"section": key, **value} for key, value in sorted(sections.items())],
        "evidence": evidence,
        "repeated_questions": sorted(question_rows, key=lambda item: (-item["reader_count"], item["sections"])),
        "question_lifecycle": lifecycle,
        "open_questions": [item for item in lifecycle if item.get("status") != "resolved"],
        "resolved_questions": [item for item in lifecycle if item.get("status") == "resolved"],
        "paragraph_consensus": sorted(consensus, key=lambda item: (item["section"], item["paragraph_id"])),
    }


def manuscript_for_editor(manuscript: Dict, max_chars: int = 220_000) -> Tuple[str, bool]:
    sections = manuscript.get("sections") or []
    lines = []
    for section in sorted(sections, key=lambda item: item.get("section_number") or 0):
        lines.append(f"\n=== SECTION {section.get('section_number')} ===")
        for paragraph in section.get("paragraph_lines") or []:
            pid = paragraph.get("paragraph_id") or f"p-{int(paragraph.get('line', 0)):06d}"
            lines.append(f"[{pid}] {paragraph.get('text', '')}")
    rendered = "\n".join(lines).strip()
    if not rendered:
        rendered = str(manuscript.get("raw_text") or "")
    truncated = len(rendered) > max_chars
    return (rendered[:max_chars] + ("\n[MANUSCRIPT TRUNCATED]" if truncated else ""), truncated)


def manuscript_editor_chunks(manuscript: Dict, max_chars: int = 70_000, max_chunks: int = 16) -> Tuple[List[Dict], bool]:
    """Render the whole manuscript into section-aware chunks without silent mid-paragraph cuts."""
    sections = sorted(manuscript.get("sections") or [], key=lambda item: item.get("section_number") or 0)
    chunks: List[Dict] = []
    current_lines: List[str] = []
    current_sections: List[int] = []

    def flush():
        if current_lines:
            chunks.append({
                "chunk": len(chunks) + 1,
                "sections": list(dict.fromkeys(current_sections)),
                "text": "\n".join(current_lines).strip(),
            })
            current_lines.clear()
            current_sections.clear()

    for section in sections:
        number = int(section.get("section_number") or 0)
        section_lines = [f"=== SECTION {number} ==="]
        for paragraph in section.get("paragraph_lines") or []:
            pid = paragraph.get("paragraph_id") or f"p-{int(paragraph.get('line', 0)):06d}"
            section_lines.append(f"[{pid}] {paragraph.get('text', '')}")
        if len("\n".join(current_lines + section_lines)) <= max_chars:
            current_lines.extend(section_lines)
            current_sections.append(number)
            continue
        flush()
        for line in section_lines:
            if current_lines and len("\n".join(current_lines + [line])) > max_chars:
                flush()
            # A single unusually large paragraph is retained as one grounded
            # unit; normal manuscript sectioning keeps this case rare.
            current_lines.append(line)
            current_sections.append(number)
    flush()

    if not chunks:
        raw = str(manuscript.get("raw_text") or "")
        chunks = [{"chunk": 1, "sections": [], "text": raw}] if raw else []
    omitted = len(chunks) > max_chunks
    return chunks[:max_chunks], omitted


def evidence_json(evidence: Dict, max_chars: int = 120_000) -> Tuple[str, bool]:
    rendered = json.dumps(evidence, ensure_ascii=False)
    if len(rendered) <= max_chars:
        return rendered, False

    # Keep the payload valid JSON while shedding the largest collection first.
    compact = {**evidence, "evidence": list(evidence.get("evidence") or [])}
    while compact["evidence"]:
        compact["evidence"] = compact["evidence"][: max(0, len(compact["evidence"]) // 2)]
        rendered = json.dumps(compact, ensure_ascii=False)
        if len(rendered) <= max_chars:
            return rendered, True

    # Very small artificial budgets used by tests can still be exceeded by
    # summaries. Return a minimal, valid description rather than sliced JSON.
    minimal = {
        "reaction_count": evidence.get("reaction_count", 0),
        "reader_count": evidence.get("reader_count", 0),
        "sections": [], "evidence": [], "repeated_questions": [],
        "paragraph_consensus": [], "truncated": True,
    }
    return json.dumps(minimal, ensure_ascii=False), True
