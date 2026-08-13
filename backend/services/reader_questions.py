"""Deterministic per-reader question lifecycle derived from reaction history."""
import hashlib
import re
from typing import Dict, List

QUESTION_STATUSES = {"open", "partially_resolved", "resolved", "reinterpreted"}
QUESTION_KINDS = {"story_question", "author_concern"}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def question_id(reader_id: str, section_number: int, question: str) -> str:
    raw = f"{reader_id}:{int(section_number)}:{_norm(question)}".encode("utf-8")
    return "q-" + hashlib.sha256(raw).hexdigest()[:20]


def question_ledger(reactions: List[Dict], reader_id: str | None = None) -> List[Dict]:
    """Replay immutable raised/update events into current questions with history."""
    rows = sorted(
        [row for row in reactions if not reader_id or row.get("reader_id") == reader_id],
        key=lambda row: (int(row.get("section_number") or 0), str(row.get("created_at") or "")),
    )
    ledger: Dict[str, Dict] = {}
    for row in rows:
        response = row.get("response_json") or {}
        rid = row.get("reader_id") or "unknown"
        reader_name = row.get("reader_name") or "Reader"
        section = int(row.get("section_number") or 0)
        events = response.get("question_events")
        if not isinstance(events, list):
            events = [
                {
                    "question_id": question_id(rid, section, text),
                    "question": text,
                    "kind": "story_question",
                    "status": "open",
                    "raised_section": section,
                }
                for text in response.get("questions_for_writer") or [] if _norm(text)
            ]
        for event in events:
            if not isinstance(event, dict) or not event.get("question_id") or not _norm(event.get("question")):
                continue
            qid = event["question_id"]
            if qid in ledger:
                continue
            ledger[qid] = {
                "question_id": qid,
                "reader_id": rid,
                "reader_name": reader_name,
                "question": str(event["question"]).strip(),
                "kind": event.get("kind") if event.get("kind") in QUESTION_KINDS else "story_question",
                "status": "open",
                "raised_section": int(event.get("raised_section") or section),
                "resolution": None,
                "resolved_section": None,
                "paragraph_id": None,
                "history": [{
                    "status": "open", "section": section,
                    "explanation": "Question raised while reading.", "paragraph_id": event.get("paragraph_id"),
                }],
            }
        for update in response.get("question_updates") or []:
            if not isinstance(update, dict) or update.get("question_id") not in ledger:
                continue
            status = update.get("status")
            if status not in QUESTION_STATUSES - {"open"}:
                continue
            entry = ledger[update["question_id"]]
            explanation = str(update.get("resolution") or "").strip()
            if not explanation:
                continue
            entry["status"] = status
            entry["resolution"] = explanation
            entry["resolved_section"] = section if status == "resolved" else None
            entry["paragraph_id"] = update.get("paragraph_id")
            entry["history"].append({
                "status": status, "section": section, "explanation": explanation,
                "paragraph_id": update.get("paragraph_id"),
            })
    return sorted(ledger.values(), key=lambda item: (item["raised_section"], item["reader_name"], item["question_id"]))


def active_questions(ledger: List[Dict], limit: int = 8) -> List[Dict]:
    return [item for item in ledger if item.get("status") != "resolved"][-limit:]
