"""One-call, provider-neutral beta-reader pipeline."""
import logging
import uuid
from typing import Dict, List

import config as _cfg
from config import db
from services.llm_gateway import structured_completion
from services.model_routing import fallback_routes_for_reader, route_for_reader, usage_record
from services.reader_contract import empty_state, merge_state, normalize_state, validate_reader_output
from services.reader_memory import count_tokens
from services.reader_prompts_v2 import build_reader_v2_prompts
from services.reader_questions import active_questions, question_ledger
from utils import now_iso

logger = logging.getLogger(__name__)


async def _latest_state(manuscript_id: str, reader_id: str) -> Dict:
    rows = await db.reader_memories.find(
        {"manuscript_id": manuscript_id, "reader_id": reader_id}, {"_id": 0}
    ).sort("section_number", -1).limit(1).to_list(1)
    if not rows:
        return empty_state()
    memory = rows[0].get("memory_json") or {}
    return normalize_state(memory.get("state") if isinstance(memory, dict) and "state" in memory else memory)


async def _reader_question_ledger(manuscript_id: str, reader_id: str) -> List[Dict]:
    rows = await db.reader_reactions.find(
        {"manuscript_id": manuscript_id, "reader_id": reader_id}, {"_id": 0}
    ).sort("section_number", 1).to_list(1000)
    return question_ledger(rows, reader_id)


def _mock_output(section_number: int, paragraphs: List[Dict]) -> Dict:
    first = paragraphs[0]
    return {
        "checking_in": "I'm curious what changes here.",
        "reading_journal": (
            f"I followed section {section_number} without losing the thread. "
            "This is deterministic V2 mock feedback for interface testing, not a literary judgment."
        ),
        "what_i_think_the_writer_is_doing": "I think the story is moving into its next beat.",
        "moments": [{
            "paragraph_id": first.get("paragraph_id") or f"p-{int(first['line']):06d}",
            "type": "reaction",
            "comment": "This opening gives me a clear point to continue from.",
        }],
        "questions_for_writer": [],
        "question_kinds": [],
        "question_updates": [],
        "state_delta": {
            "facts": [f"Completed section {section_number}."],
            "impressions": ["The story remains readable."],
            "open_threads": ["What changes next."],
            "emotional_state": ["curious"],
        },
    }


async def get_reader_reaction_v2(reader: Dict, section: Dict, genre: str, manuscript_id: str) -> Dict:
    paragraphs: List[Dict] = section.get("paragraph_lines") or []
    if not paragraphs:
        raise ValueError("Reader V2 requires at least one paragraph")
    section_number = int(section["section_number"])
    previous_state = await _latest_state(manuscript_id, reader["id"])
    prior_questions = active_questions(await _reader_question_ledger(manuscript_id, reader["id"]))
    route = route_for_reader(reader)
    system, user = build_reader_v2_prompts(
        reader, genre, section_number, int(section.get("total_sections") or 1), paragraphs, previous_state, prior_questions
    )
    if _cfg.MOCK_LLM:
        raw = _mock_output(section_number, paragraphs)
        usage = usage_record(route, "reader", count_tokens(system + user), count_tokens(str(raw)))
    else:
        attempted_routes = []
        last_error = None
        for candidate in fallback_routes_for_reader(reader):
            attempted_routes.append(candidate.key)
            try:
                completion = await structured_completion(
                    route=candidate,
                    role="reader",
                    system_prompt=system,
                    user_prompt=user,
                    max_tokens=2600,
                )
                route = candidate
                raw, usage = completion.data, completion.usage
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Reader %s section %s failed on %s: %s",
                    reader.get("id"), section_number, candidate.key, exc,
                )
        else:
            attempted = ", ".join(attempted_routes)
            raise RuntimeError(f"All configured reader models failed ({attempted}): {last_error}") from last_error

    response, warnings = validate_reader_output(
        raw, paragraphs, open_questions=prior_questions,
        reader_id=reader["id"], section_number=section_number,
    )
    state = merge_state(previous_state, response.pop("state_delta"))
    response_json = {
        **response,
        "pipeline_version": "v2",
        "model": {"provider": route.provider, "model": route.model},
        "usage": usage.to_dict(),
    }
    inline_comments = [
        {"line": m["paragraph"], "paragraph_id": m["paragraph_id"], "type": m["type"], "comment": m["comment"]}
        for m in response["moments"]
    ]
    reaction_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "reader_name": (reader.get("name") or "Reader").strip(),
        "section_number": section_number,
        "inline_comments": inline_comments,
        "section_reflection": response["reading_journal"],
        "response_json": response_json,
        "created_at": now_iso(),
    }
    await db.reader_reactions.insert_one(reaction_doc)
    await db.reader_memories.insert_one({
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "section_number": section_number,
        "memory_json": {"schema_version": 2, "state": state},
        "created_at": now_iso(),
    })
    return {
        "reader_id": reader["id"],
        "reader_name": reaction_doc["reader_name"],
        "avatar_index": reader.get("avatar_index", 0),
        "personality": reader.get("personality", ""),
        "section_number": section_number,
        **response,
        "inline_comments": inline_comments,
        "section_reflection": response["reading_journal"],
        "reaction_id": reaction_doc["id"],
        "model": response_json["model"],
        "usage": response_json["usage"],
        "_parse_warning": bool(warnings),
    }
