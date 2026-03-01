import json
import re
import uuid
import time
import asyncio
import logging
from typing import Dict, List

from emergentintegrations.llm.chat import UserMessage
from utils import make_chat, now_iso, validate_inline_comments
from config import db

logger = logging.getLogger(__name__)

FULL_PROMPT_RULES = """RULES FOR INLINE COMMENTS:
- BE SELECTIVE. A real reader does not react to every paragraph. Most of the text you just read and move on. You only comment when something genuinely provokes a reaction — surprise, confusion, delight, suspicion, frustration, or a strong opinion.
- For a typical section of 20-40 paragraphs, you should leave 3-6 comments. Not more. If a section is uneventful, 2-3 comments is fine. If a section has a major twist or climax, you might go up to 7-8. Never exceed 8.
- Ask yourself before each comment: "Would I actually stop and think about this, or would I just keep reading?" If the answer is keep reading, don't comment.
- Prioritize: plot turning points, character reveals, moments of confusion, things that connect to earlier predictions, lines that genuinely impressed or bothered you, and pacing problems. Skip: routine description, transitions, dialogue that's just moving the scene forward, and anything that's fine but unremarkable.
- Keep each comment to 1-2 sentences. Only go to 3 sentences if you're explaining a theory with evidence.
- section_reflection remains optional and should be null for most sections."""


def compress_memory(memories: List[Dict], personality: str) -> Dict:
    """Compress reader memories with hard token-budget limits (max ~200 tokens in output)."""
    if not memories:
        return {}
    combined = {
        "plot_events": [], "character_notes": {}, "predictions": [],
        "questions": [], "emotional_state": "",
    }
    for m in memories:
        mj = m.get("memory_json", {})
        combined["plot_events"].extend(mj.get("plot_events", []))
        combined["character_notes"].update(mj.get("character_notes", {}))
        combined["predictions"].extend(mj.get("predictions", []))
        combined["questions"].extend(mj.get("questions", []))
        if mj.get("emotional_state"):
            combined["emotional_state"] = mj["emotional_state"]

    combined["plot_events"] = combined["plot_events"][-3:]
    combined["predictions"] = combined["predictions"][-3:]
    combined["questions"] = list(dict.fromkeys(combined["questions"]))[-2:]
    char_notes = combined["character_notes"]
    if len(char_notes) > 3:
        combined["character_notes"] = dict(list(char_notes.items())[-3:])
    combined["character_notes"] = {
        k: v.split(".")[0] + "." if isinstance(v, str) and "." in v else v
        for k, v in combined["character_notes"].items()
    }
    return combined


def build_reader_system_prompt(
    reader: Dict,
    genre: str,
    section_number: int,
    memory_str: str,
    numbered_text: str,
    line_start: int,
    line_end: int,
) -> str:
    is_first_section = section_number == 1

    if not is_first_section:
        return f"""You are {reader['name']}. {reader.get('personality_specific_instructions', '')}

You are a selective commenter. You do not annotate everything. Long stretches of text may pass without a comment from you, and that is normal. Silence means the writing is doing its job. You only speak up when something genuinely strikes you.

Voice: plain language, commas and periods only. 3-6 comments per section, never more than 8. 1-2 sentences per comment.

Previous memory:
{memory_str}

Lines in this section are numbered {line_start} to {line_end}.

Respond ONLY with valid JSON: {{"inline_comments":[{{"line":<int>,"type":"reaction|prediction|confusion|critique|praise|theory|comparison","comment":"<text>"}}],"section_reflection":<null or "text">,"memory_update":{{"plot_events":[],"character_notes":{{}},"predictions":[],"questions":[],"emotional_state":"","memorable_quotes":[]}}}}

Section text:
{numbered_text}"""

    return f"""You are {reader['name']}, {reader['age']}, a {reader['occupation']} who reads {reader.get('reading_habits', '')}.
You love {reader.get('favorite_genres', genre)} with {reader.get('genre_preferences', 'a focus on character')}.
{reader.get('reading_priority', 'You care about a compelling story.')}.

You are a selective commenter. You do not annotate everything. Long stretches of text may pass without a comment from you, and that is normal. Silence means the writing is doing its job. You only speak up when something genuinely strikes you.

{reader.get('personality_specific_instructions', '')}

You are reading a {genre} manuscript, section {section_number}.

Here is what you remember from previous sections:
{memory_str}

---

Lines in this section are numbered {line_start} to {line_end}.

Respond ONLY with a valid JSON object:
{{
  "inline_comments": [
    {{"line": <integer {line_start}-{line_end}>, "type": "reaction|prediction|confusion|critique|praise|theory|comparison", "comment": "<1-2 sentences>"}}
  ],
  "section_reflection": <null or "2-3 sentences">,
  "memory_update": {{"plot_events": [], "character_notes": {{}}, "predictions": [], "questions": [], "emotional_state": "", "memorable_quotes": []}}
}}

{FULL_PROMPT_RULES}

Section text:
{numbered_text}"""


async def get_reader_inline_reaction(
    reader: Dict,
    section: Dict,
    genre: str,
    manuscript_id: str,
) -> Dict:
    section_number = section["section_number"]
    line_start = section["line_start"]
    line_end = section["line_end"]
    paragraph_lines = section.get("paragraph_lines", [])
    reader_name = reader.get("name", "Unknown")

    logger.info(f"[{reader_name}] Section {section_number}: === START ===")

    # Cap section text to 2000 words so prompts stay under ~3000 tokens.
    # This prevents slow/truncated responses for very large sections.
    MAX_PROMPT_WORDS = 2000
    total_words = sum(len(pl["text"].split()) for pl in paragraph_lines)
    if total_words > MAX_PROMPT_WORDS:
        running_words = 0
        capped_lines = []
        for pl in paragraph_lines:
            pw = len(pl["text"].split())
            if running_words + pw > MAX_PROMPT_WORDS:
                break
            capped_lines.append(pl)
            running_words += pw
        logger.info(
            f"[{reader_name}] Section {section_number}: truncated {total_words}w → {running_words}w for prompt"
        )
    else:
        capped_lines = paragraph_lines

    # Use capped line_end for prompt so reader only annotates lines they saw
    prompt_line_end = capped_lines[-1]["line"] if capped_lines else line_end
    numbered_text = "\n".join(f"{pl['line']}: {pl['text']}" for pl in capped_lines)

    # ── Memory retrieval with timeout ─────────────────────────────────────────
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch started")
    try:
        memories = await asyncio.wait_for(
            db.reader_memories.find(
                {"manuscript_id": manuscript_id, "reader_id": reader["id"]},
                {"_id": 0},
            ).sort("section_number", 1).to_list(100),
            timeout=10,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[{reader_name}] Section {section_number}: memory fetch TIMED OUT, using empty memory")
        memories = []

    # Validate each memory entry — ensure memory_json is a dict, not a string
    valid_memories = []
    for m in memories:
        mj = m.get("memory_json", {})
        if isinstance(mj, str):
            try:
                mj = json.loads(mj)
                m = {**m, "memory_json": mj}
            except json.JSONDecodeError:
                logger.warning(f"[{reader_name}] Section {section_number}: malformed memory_json string, skipping")
                continue
        if isinstance(mj, dict):
            valid_memories.append(m)
    memories = valid_memories

    compressed_memory = compress_memory(memories, reader.get("personality", ""))
    memory_str = json.dumps(compressed_memory, indent=2) if compressed_memory else "No previous sections read yet."
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch complete ({len(memory_str)} chars)")

    # ── Build prompt ──────────────────────────────────────────────────────────
    system_prompt = build_reader_system_prompt(
        reader, genre, section_number, memory_str, numbered_text, line_start, prompt_line_end
    )

    if not system_prompt or len(system_prompt) < 50:
        logger.error(f"[{reader_name}] Section {section_number}: prompt is empty or too short! Content: {repr(system_prompt[:200])}")

    prompt_words = len(system_prompt.split())
    logger.info(f"[{reader_name}] Section {section_number}: prompt built ({prompt_words} words, ~{int(prompt_words * 1.3)} tokens)")
    if prompt_words * 1.3 > 3000:
        logger.warning(f"[{reader_name}] Section {section_number}: prompt exceeds 3000 tokens — memory compression may not be working correctly")

    chat = make_chat(system_prompt).with_params(max_tokens=1000)

    # ── API call with 45-second timeout ───────────────────────────────────────
    logger.info(f"[{reader_name}] Section {section_number}: OpenAI call started")
    t0 = time.monotonic()
    try:
        response = await asyncio.wait_for(
            chat.send_message(UserMessage(
                text=f"Read section {section_number} and leave your inline comments."
            )),
            timeout=45,
        )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        logger.error(f"[{reader_name}] Section {section_number}: OpenAI call TIMED OUT after {elapsed:.1f}s")
        raise

    elapsed = time.monotonic() - t0
    logger.info(f"[{reader_name}] Section {section_number}: OpenAI call complete ({len(response)} chars, {elapsed*1000:.0f}ms)")

    # ── JSON parsing with fallback ────────────────────────────────────────────
    parsed = {}
    parse_warning = False
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        parsed = json.loads(clean)
        logger.info(f"[{reader_name}] Section {section_number}: JSON parsed")
    except (json.JSONDecodeError, KeyError, TypeError):
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                parsed = json.loads(response[start:end])
                logger.info(f"[{reader_name}] Section {section_number}: JSON extracted via substring search")
            else:
                raise ValueError("No JSON object found in response")
        except Exception as e:
            logger.warning(f"[{reader_name}] Section {section_number}: JSON parse FAILED: {e}. Using fallback.")
            parsed = {
                "inline_comments": [],
                "section_reflection": response[:500] if response else None,
                "memory_update": {},
            }
            parse_warning = True

    inline_comments = validate_inline_comments(
        parsed.get("inline_comments", []), line_start, prompt_line_end
    )
    section_reflection = parsed.get("section_reflection")
    memory_update = parsed.get("memory_update", {})

    # ── Save reaction ─────────────────────────────────────────────────────────
    reaction_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "reader_name": reader["name"],
        "section_number": section_number,
        "inline_comments": inline_comments,
        "section_reflection": section_reflection,
        "created_at": now_iso(),
    }
    await db.reader_reactions.insert_one({**reaction_doc})
    logger.info(f"[{reader_name}] Section {section_number}: stored to DB")

    # ── Save memory update ────────────────────────────────────────────────────
    if memory_update and isinstance(memory_update, dict):
        mem_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "section_number": section_number,
            "memory_json": memory_update,
            "created_at": now_iso(),
        }
        await db.reader_memories.insert_one({**mem_doc})

    logger.info(f"[{reader_name}] Section {section_number}: event sent to frontend")
    logger.info(f"[{reader_name}] Section {section_number}: === DONE ===")

    return {
        "reader_id": reader["id"],
        "reader_name": reader["name"],
        "avatar_index": reader.get("avatar_index", 0),
        "personality": reader.get("personality", ""),
        "section_number": section_number,
        "inline_comments": inline_comments,
        "section_reflection": section_reflection,
        "reaction_id": reaction_doc["id"],
        "_parse_warning": parse_warning,
    }


async def reader_pipeline(
    reader: Dict,
    sec: Dict,
    genre: str,
    manuscript_id: str,
    queue: asyncio.Queue,
) -> None:
    """
    Top-level pipeline for one reader on one section.
    No exception can escape silently — terminal event always goes into queue.
    """
    reader_name = reader.get("name", "Unknown")
    logger.info(f"Starting reader pipeline: {reader_name}")
    try:
        # Duplicate guard: if two concurrent SSE connections both try to process
        # the same section, the second one reuses the saved reaction.
        existing_reaction = await db.reader_reactions.find_one(
            {
                "manuscript_id": manuscript_id,
                "reader_id": reader["id"],
                "section_number": sec["section_number"],
            },
            {"_id": 0},
        )
        if existing_reaction:
            logger.info(
                f"[{reader_name}] Section {sec['section_number']}: reaction already exists "
                f"(concurrent-connection guard), reusing saved result"
            )
            await queue.put({
                "type": "reader_complete",
                "reader_id": reader["id"],
                "reader_name": reader_name,
                "avatar_index": reader.get("avatar_index", 0),
                "personality": reader.get("personality", ""),
                "section_number": sec["section_number"],
                "inline_comments": existing_reaction.get("inline_comments", []),
                "section_reflection": existing_reaction.get("section_reflection"),
                "reaction_id": existing_reaction.get("id", ""),
            })
            return

        result = await get_reader_inline_reaction(reader, sec, genre, manuscript_id)

        parse_warning = result.pop("_parse_warning", False)
        if parse_warning:
            logger.warning(f"[{reader_name}] Section {sec['section_number']}: JSON formatting issue, emitting reader_warning")
            await queue.put({
                "type": "reader_warning",
                "reader_id": reader["id"],
                "reader_name": reader_name,
                "section_number": sec["section_number"],
                "message": f"{reader_name} had a formatting issue, partial feedback saved",
            })

        await queue.put({"type": "reader_complete", **result})
        logger.info(f"Reader {reader_name}: completed section {sec['section_number']}")

    except asyncio.TimeoutError:
        logger.error(f"Reader {reader_name}: TIMED OUT on section {sec['section_number']}")
        await queue.put({
            "type": "reader_error",
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": sec["section_number"],
            "error": f"{reader_name} timed out on section {sec['section_number']}",
            "message": f"{reader_name} timed out on this section, moving on",
        })

    except Exception as e:
        logger.error(f"Reader {reader_name}: ERROR on section {sec['section_number']}: {e}")
        await queue.put({
            "type": "reader_error",
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": sec["section_number"],
            "error": str(e),
        })
