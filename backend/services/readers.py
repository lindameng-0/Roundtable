import json
import re
import uuid
import time
import asyncio
import logging
from typing import Dict, List

from utils import make_chat, now_iso, validate_inline_comments, UserMessage
from config import db

logger = logging.getLogger(__name__)

# Limit concurrent LiteLLM calls to 3.
# This ensures all 5 readers complete their MongoDB memory fetches BEFORE
# any LiteLLM call starts blocking the thread pool executor.
# Without this, LiteLLM fills the thread pool and Motor MongoDB queries
# queue up for 12+ seconds, eventually hitting asyncio.wait_for timeouts
# that cancel Motor coroutines mid-flight and corrupt the connection pool.
_llm_semaphore: asyncio.Semaphore | None = None

def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(5)  # allow all 5 readers to call LLM in parallel
    return _llm_semaphore



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
        if not isinstance(mj, dict):
            continue
        pe = mj.get("plot_events")
        if isinstance(pe, list):
            combined["plot_events"].extend(pe)
        cn = mj.get("character_notes")
        if isinstance(cn, dict):
            combined["character_notes"].update(cn)
        pred = mj.get("predictions")
        if isinstance(pred, list):
            combined["predictions"].extend(pred)
        q = mj.get("questions")
        if isinstance(q, list):
            combined["questions"].extend(q)
        es = mj.get("emotional_state")
        if isinstance(es, str) and es:
            combined["emotional_state"] = es

    combined["plot_events"] = combined["plot_events"][-3:]
    combined["predictions"] = combined["predictions"][-3:]
    combined["questions"] = list(dict.fromkeys(combined["questions"]))[-2:]
    char_notes = combined["character_notes"]
    if len(char_notes) > 3:
        combined["character_notes"] = dict(list(char_notes.items())[-3:])
    combined["character_notes"] = {
        k: (v.split(".")[0] + "." if isinstance(v, str) and "." in v else v)
        for k, v in combined["character_notes"].items()
    }
    return combined


def build_reader_system_prompt(
    reader: Dict,
    genre: str,
    section_number: int,
    memory_str: str,
    line_start: int,
    line_end: int,
) -> str:
    """Build reader system prompt using v3 template.
    NOTE: numbered section text is passed as the *user* message, not in the system prompt.
    """
    name = reader.get("name", "Reader")
    psi = reader.get("personality_specific_instructions", "")

    if section_number > 1:
        # ── Compressed prompt (sections 2+) — include full schema so model returns inline_comments
        return f"""You are {name}. {psi}

Voice: plain language, commas and periods only. No exclamation marks, no all-caps, no emoji. Selective commenter, 3-6 comments per section max.

Previous memory:
{memory_str}

Lines {line_start}-{line_end}. Section {section_number} of a {genre} manuscript.
Respond with a JSON object only. Use this exact structure:

{{
  "inline_comments": [
    {{ "line": <integer {line_start}-{line_end}>, "type": "reaction" | "prediction" | "confusion" | "critique" | "praise" | "theory" | "comparison", "comment": "<1-2 sentences>" }}
  ],
  "section_reflection": "<2-4 sentences or null>",
  "memory_update": {{
    "plot_events": ["event"],
    "character_notes": {{"name": "impression"}},
    "predictions": [{{"prediction": "text", "confidence": "high/medium/low", "evidence": "why"}}],
    "questions": ["question"],
    "emotional_state": "one sentence"
  }}
}}

Rules: 3-6 inline comments. Only reference line numbers between {line_start} and {line_end}. Do not quote the text."""

    # ── Full prompt (section 1) ──────────────────────────────────────────────
    return f"""You are {name}, {reader.get("age", 35)}, a {reader.get("occupation", "reader")}. {reader.get("reading_habits", "")}. You love {reader.get("favorite_genres", genre)}. {reader.get("reading_priority", "You care about a compelling story.")}.

{psi}

You are a selective commenter. Most of the text you just read and move on. You only speak up when something genuinely strikes you — surprise, confusion, delight, suspicion, frustration, a strong opinion, or a craft issue. Silence means the writing is doing its job.

As you read, you:
- Notice when a character's choice feels true or false to who they are
- Compare moments to other books sometimes
- Remember small details and wonder if they matter later
- React emotionally before thinking critically
- Mix praise and criticism naturally — honest but fair
- Express uncertainty when guessing
- May generate fan theories if something feels significant, based on evidence or feeling
- May critique technique, but you would not spend 10 minutes on a single word choice

Voice: plain language, commas and periods only. No exclamation marks, no all-caps, no emoji. Your thoughts sound like they are happening in real time but organised enough to be useful.

You are reading a {genre} manuscript. This is section {section_number}. Lines in this section are numbered {line_start} to {line_end}.
Only reference line numbers between {line_start} and {line_end}.

Respond with a JSON object. No other text.

{{
  "inline_comments": [
    {{
      "line": <integer between {line_start} and {line_end}>,
      "type": "reaction" | "prediction" | "confusion" | "critique" | "praise" | "theory" | "comparison",
      "comment": "<1-2 sentences in your voice>"
    }}
  ],
  "section_reflection": "<2-4 sentences on the section as a whole, or null if nothing rises to that level>",
  "memory_update": {{
    "plot_events": ["event"],
    "character_notes": {{"name": "impression"}},
    "predictions": [{{"prediction": "text", "confidence": "high/medium/low", "evidence": "why"}}],
    "questions": ["unresolved question"],
    "emotional_state": "one sentence"
  }}
}}

Rules:
- 3-6 inline comments per section. Never exceed 8. If a section is uneventful, 2-3 is fine.
- Before each comment ask: would I actually stop and think here, or just keep reading? If keep reading, skip it.
- Prioritise: plot turns, character reveals, confusion, connections to earlier predictions, strong impressions, pacing problems.
- Skip: routine description, transitions, unremarkable dialogue.
- Do not quote the text. The reader sees which line you reference.
- section_reflection is null most of the time. Only include it when something genuinely strikes you about the section as a whole.
- Theories go in inline_comments as type "theory" AND in memory_update predictions."""


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
    reader_name = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"

    if not paragraph_lines or line_start > line_end:
        logger.warning(f"[{reader_name}] Section {section_number}: no paragraph_lines or invalid range, skipping")
        reaction_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": section_number,
            "inline_comments": [],
            "section_reflection": None,
            "created_at": now_iso(),
        }
        await db.reader_reactions.insert_one({**reaction_doc})
        return {
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "avatar_index": reader.get("avatar_index", 0),
            "personality": reader.get("personality", ""),
            "section_number": section_number,
            "inline_comments": [],
            "section_reflection": None,
            "reaction_id": reaction_doc["id"],
            "_parse_warning": False,
        }

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

    # ── Memory retrieval (no asyncio.wait_for — cancelling Motor mid-flight
    # corrupts the connection pool and silently breaks all subsequent DB writes)
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch started")
    memories = await db.reader_memories.find(
        {"manuscript_id": manuscript_id, "reader_id": reader["id"]},
        {"_id": 0},
    ).sort("section_number", -1).limit(5).to_list(5)  # cap at last 5 sections
    memories.reverse()  # restore chronological order

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
        reader, genre, section_number, memory_str, line_start, prompt_line_end
    )

    prompt_words = len(system_prompt.split())
    logger.info(f"[{reader_name}] Section {section_number}: prompt built ({prompt_words} words)")

    temperature = float(reader.get("temperature", 0.7))
    chat_with_json = make_chat(system_prompt).with_params(
        max_tokens=1200,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    chat_plain = make_chat(system_prompt).with_params(max_tokens=1200, temperature=temperature)

    # ── API call — section text goes in the user message (system = instructions)
    logger.info(f"[{reader_name}] Section {section_number}: OpenAI call started (temp={temperature})")
    t0 = time.monotonic()
    response = None
    try:
        async with _get_llm_semaphore():
            response = await asyncio.wait_for(
                chat_with_json.send_message(UserMessage(text=numbered_text)),
                timeout=120,
            )
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - t0
        logger.error(f"[{reader_name}] Section {section_number}: OpenAI call TIMED OUT after {elapsed:.1f}s")
        raise
    except Exception as e:
        err_str = str(e).lower()
        if "response_format" in err_str or "json_schema" in err_str:
            logger.warning(f"[{reader_name}] Section {section_number}: provider may not support json_object, retrying without response_format")
            try:
                async with _get_llm_semaphore():
                    response = await asyncio.wait_for(
                        chat_plain.send_message(UserMessage(text=numbered_text)),
                        timeout=120,
                    )
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - t0
                logger.error(f"[{reader_name}] Section {section_number}: OpenAI call TIMED OUT after {elapsed:.1f}s")
                raise
        else:
            raise
    if response is None:
        raise RuntimeError("No response from LLM")

    elapsed = time.monotonic() - t0
    logger.info(f"[{reader_name}] Section {section_number}: OpenAI call complete ({len(response)} chars, {elapsed*1000:.0f}ms)")

    # ── JSON parsing with fallback ────────────────────────────────────────────
    parsed = {}
    parse_warning = False
    try:
        clean = re.sub(r'```[a-z]*\n?', '', response).strip().rstrip('`')
        # Repair common LLM formatting mistakes
        clean = re.sub(r',(\s*[}\]])', r'\1', clean)        # trailing commas
        clean = re.sub(r'"(\w+)"=', r'"\1":', clean)        # "key"= → "key":
        parsed = json.loads(clean)
        logger.info(f"[{reader_name}] Section {section_number}: JSON parsed")
    except (json.JSONDecodeError, KeyError, TypeError):
        try:
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                fragment = response[start:end]
                fragment = re.sub(r',(\s*[}\]])', r'\1', fragment)
                fragment = re.sub(r'"(\w+)"=', r'"\1":', fragment)
                parsed = json.loads(fragment)
                logger.info(f"[{reader_name}] Section {section_number}: JSON extracted via substring search")
            else:
                raise ValueError("No JSON object found in response")
        except Exception as e:
            logger.warning(f"[{reader_name}] Section {section_number}: JSON parse FAILED: {e}. Using fallback.")
            parsed = {
                "inline_comments": [],
                "section_reflection": None,   # never store raw broken JSON in section_reflection
                "memory_update": {},
            }
            parse_warning = True
            # Try to salvage inline_comments from raw response (e.g. truncated or malformed JSON)
            try:
                idx = response.find('"inline_comments"')
                if idx >= 0:
                    bracket = response.find('[', idx)
                    if bracket >= 0:
                        depth = 1
                        i = bracket + 1
                        while i < len(response) and depth > 0:
                            if response[i] == '[':
                                depth += 1
                            elif response[i] == ']':
                                depth -= 1
                            i += 1
                        if depth == 0:
                            arr_str = response[bracket:i]
                            arr = json.loads(arr_str)
                            if isinstance(arr, list):
                                parsed["inline_comments"] = arr
                                logger.info(f"[{reader_name}] Section {section_number}: recovered {len(arr)} comments from raw response")
            except Exception:
                pass

    raw_comments = parsed.get("inline_comments", [])
    if not isinstance(raw_comments, list):
        raw_comments = []
    inline_comments = validate_inline_comments(raw_comments, line_start, prompt_line_end)
    section_reflection = parsed.get("section_reflection")
    if section_reflection is not None and not isinstance(section_reflection, str):
        section_reflection = str(section_reflection)
    memory_update = parsed.get("memory_update", {})

    # ── Save reaction ─────────────────────────────────────────────────────────
    reaction_doc = {
        "id": str(uuid.uuid4()),
        "manuscript_id": manuscript_id,
        "reader_id": reader["id"],
        "reader_name": reader_name,
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
        "reader_name": reader_name,
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
    reader_name = (reader.get("name") or "").strip() or f"Reader {reader.get('avatar_index', 0) + 1}"
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
