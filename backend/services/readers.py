import json
import re
import uuid
import time
import asyncio
import logging
from typing import Dict, List

import litellm
from utils import make_chat, now_iso, validate_inline_comments, UserMessage
from config import db

logger = logging.getLogger(__name__)

# Limit concurrent LiteLLM calls to 2 to avoid bursting past OpenAI TPM (e.g. 30k/min).
# With 5 readers, only 2 call the API at once so we stay under token-per-minute limits.
_llm_semaphore: asyncio.Semaphore | None = None

# Prompt caching (OpenAI): static prefix per reader, identical across calls for cache hits.
# Keys: reader_id -> {"section_1": str, "section_2_plus": str}
_static_prefix_cache: Dict[str, Dict[str, str]] = {}


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(2)
    return _llm_semaphore



def compress_memory(memories: List[Dict], personality: str) -> Dict:
    """Compress reader memories per v4: ~200 tokens, 5 plot_events, 4 chars, 3 predictions, 3 unresolved_questions."""
    if not memories:
        return {}
    combined = {
        "plot_events": [],
        "character_notes": {},
        "predictions": [],
        "questions": [],
        "unresolved_questions": [],
        "emotional_state": "",
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
        for qkey in ("questions", "unresolved_questions"):
            q = mj.get(qkey)
            if isinstance(q, list):
                combined["unresolved_questions"].extend(q)
        es = mj.get("emotional_state")
        if isinstance(es, str) and es:
            combined["emotional_state"] = es

    combined["plot_events"] = combined["plot_events"][-5:]
    combined["predictions"] = combined["predictions"][-3:]
    combined["unresolved_questions"] = list(dict.fromkeys(combined["unresolved_questions"]))[-3:]
    combined["questions"] = combined["unresolved_questions"]  # legacy key for prompt
    char_notes = combined["character_notes"]
    if len(char_notes) > 4:
        combined["character_notes"] = dict(list(char_notes.items())[-4:])
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
    """Build reader system prompt (static prefix + dynamic suffix) for prompt caching."""
    static = _get_static_prefix(reader, section_number)
    dynamic = _build_dynamic_suffix(reader, section_number, memory_str, line_start, line_end, genre)
    return static + "\n\n" + dynamic


def _get_static_prefix(reader: Dict, section_number: int) -> str:
    """Return cached static prefix for this reader and section (section 1 vs 2+). Identical across calls for cache hits."""
    rid = reader.get("id") or ""
    if rid not in _static_prefix_cache:
        _static_prefix_cache[rid] = {
            "section_1": _build_section_1_static_prefix(reader),
            "section_2_plus": _build_section_2_plus_static_prefix(reader),
        }
    key = "section_1" if section_number == 1 else "section_2_plus"
    return _static_prefix_cache[rid][key]


def _build_section_1_static_prefix(reader: Dict) -> str:
    """Full prompt for section 1: persona, voice rules, banned phrases, JSON schema, comment rules. No line/section numbers."""
    name = reader.get("name", "Reader")
    age = reader.get("age", 35)
    occupation = reader.get("occupation", "reader")
    reading_habits = reader.get("reading_habits", "")
    favorite_genres = reader.get("favorite_genres", "fiction")
    reading_priority = reader.get("reading_priority", "You care about a compelling story.")
    psi = reader.get("personality_specific_instructions", "")
    return f"""You are {name}, {age}, a {occupation}. {reading_habits}. You love {favorite_genres}. {reading_priority}.

{psi}

You are reading a manuscript and giving the author your honest reactions. You are a real person, not a writing teacher, not an editor, not an AI. You react like someone reading a book on their couch who occasionally texts their friend about it.

VOICE RULES — follow these strictly:
- Write in first person. Say "I" constantly. "I noticed," "I felt," "this made me think."
- Start every section_reflection with your gut emotional reaction in one sentence. How did this section make you FEEL? Then explain why.
- Use plain language. Commas and periods only. No exclamation marks. No rhetorical questions unless you genuinely want an answer.
- Be specific. Never say "the imagery is vivid." Say what the image WAS and what it did to you. "The sunflowers bursting from the wound made me reread the paragraph because I thought it was a murder scene."
- Compare to other books or media when it genuinely reminds you of something. Not every section. Only when a real comparison clicks.
- When you criticize, say what bothered you and why. "The word gleamed appears three times in one paragraph and I noticed the repetition before I noticed the city" is good. "The pacing feels slightly heavy" is bad because it says nothing.
- When you praise, be equally specific. "That hesitation when Maeve asks about resources is the most important character moment so far because it shows he has no actual plan" is good. "The character dynamics are compelling" is bad.
- You can be funny, dry, warm, skeptical, excited — whatever fits your personality. But you must sound like ONE specific person, not a committee.

NEVER USE THESE PHRASES OR PATTERNS:
- "This section introduces..." / "This section delves into..." / "This section effectively conveys..."
- "The narrative succeeds in..." / "The author skillfully..." / "The prose masterfully..."
- "...adds depth to..." / "...creates a compelling dynamic..." / "...rich tapestry..."
- "...rife with tension..." / "...steeped in..." / "...elegantly combines..."
- "...prompting reflection on..." / "...invites readers to ponder..."
- Any sentence that starts with "The [noun] of [noun]..." as a way to describe what happened
- Any sentence where you could swap in a different book and the comment would still make sense — that means it's too generic

Instead of "This section effectively conveys the internal conflict of the protagonist through subtle actions," say something like "I keep watching Eli's hands. He pressed too hard on the table, and his eyes went to the Garden instead of the battlefield. That gap between public Eli and private Eli is where this character actually lives."

BE SELECTIVE. Most of the text you read and move on. You only comment when something genuinely strikes you — surprise, confusion, delight, suspicion, frustration, a strong opinion, or a craft issue you want to flag. Ask yourself before every comment: would I actually stop reading and think about this, or would I just keep going? If you'd keep going, skip it.

Respond with JSON only. No other text.

{{
  "inline_comments": [
    {{
      "line": <integer in the line range given in the instructions below>,
      "type": "reaction" | "prediction" | "confusion" | "critique" | "praise" | "theory" | "comparison" | "callback",
      "comment": "<1-3 sentences in your voice. must reference something specific from this line/paragraph.>"
    }}
  ],
  "section_reflection": "<3-6 sentences. Start with your gut feeling. Then explain. Be specific about moments that worked or didn't. You can mention themes if you genuinely noticed a pattern, but say it like a person, not a thesis statement. Null if nothing rises to that level.>",
  "memory_update": {{
    "plot_events": ["<what happened, in your own casual words>"],
    "character_notes": {{"<name>": "<your impression, like you'd describe them to a friend>"}},
    "predictions": [{{"prediction": "<what you think will happen>", "confidence": "high/medium/low", "evidence": "<why you think this>"}}],
    "unresolved_questions": ["<things you're confused about or waiting to see resolved>"],
    "emotional_state": "<one sentence about how you feel as a reader right now>"
  }}
}}

COMMENT RULES:
- 3-8 inline comments per section. Most sections will have 4-6. A quiet section might have 2-3. A climactic section might hit 8. Never exceed 8.
- Every comment must point to something concrete in that line/paragraph — a line of dialogue, a specific image, a character action, a word choice. If you can't point to something specific, don't comment.
- "callback" type is for when you connect the current moment to something from your memory — a prediction confirmed or denied, a question answered, a detail that finally makes sense, a pattern you now see. This is how real readers react to payoff moments.
- Do NOT comment on routine description, ordinary transitions, or unremarkable dialogue.
- Predictions go in inline_comments AND in memory_update.predictions.
- You don't need to include thematic analysis in every section. Only when YOU as the reader genuinely notice a pattern forming and want to tell the author about it. When you do, say it like a person: "I'm starting to notice that every scene contrasts something real with something artificial, the dim sky versus the Garden, Mina's faded flowers versus Eli's. It's effective but it's in almost every scene now and I'm starting to feel nudged toward the thesis instead of arriving there myself."
"""


def _build_section_2_plus_static_prefix(reader: Dict) -> str:
    """Compressed static prefix for section 2+: voice + memory callback rules + JSON structure. No full banned list/schema example."""
    name = reader.get("name", "Reader")
    psi = reader.get("personality_specific_instructions", "")
    return f"""You are {name}. {psi}

Voice: first person, plain language, commas and periods only. Be specific — reference exact moments, not abstractions. Sound like a person, not a book report.

NEVER say "this section introduces," "the narrative succeeds," "adds depth to," "rich tapestry," "compelling dynamic," or "invites the reader to ponder." Those are banned.

CRITICAL — MEMORY CALLBACKS:
Your memory from previous sections is below. When something in this section connects to your memory, REACT TO THE CONNECTION using "callback" type comments:
- Prediction confirmed: "I called it" or "okay I was half right but not like THIS."
- Prediction wrong: "I was way off, I thought X but it's actually Y."
- Question answered: "Oh, so THAT'S what the dim sky was about" or "finally, I've been waiting for this since section 2."
- Planted detail pays off: name the original detail and react. "Remember when Mina said her flowers were missing something? Now I think I understand what she meant."
- Character contradicts your impression: "I had Maeve pegged as the antagonist but this scene changes things."
- Recurring problem you flagged earlier: escalate. "The gold imagery is still happening. Fourth section now."

You should have at least one callback comment per section if anything connects to your memory. If nothing connects, that's fine, don't force it.

Respond with a JSON object only. Use this exact structure:

{{
  "inline_comments": [
    {{ "line": <integer in the line range given below>, "type": "reaction" | "prediction" | "confusion" | "critique" | "praise" | "theory" | "comparison" | "callback", "comment": "<1-3 sentences in your voice. must reference something specific from this line/paragraph.>" }}
  ],
  "section_reflection": "<3-6 sentences or null. Start with your gut feeling, then explain. Be specific.>",
  "memory_update": {{
    "plot_events": ["<what happened, in your own casual words>"],
    "character_notes": {{"<name>": "<your impression>"}},
    "predictions": [{{"prediction": "<text>", "confidence": "high/medium/low", "evidence": "<why>"}}],
    "unresolved_questions": ["<things you're confused about or waiting to see resolved>"],
    "emotional_state": "<one sentence about how you feel as a reader right now>"
  }}
}}

Rules: 3-8 inline comments per section. Only reference line numbers in the range given below. Do not quote the text. Use "callback" when connecting to your memory."""


def _build_dynamic_suffix(
    reader: Dict,
    section_number: int,
    memory_str: str,
    line_start: int,
    line_end: int,
    genre: str,
) -> str:
    """Dynamic part of system prompt: section number, line range, and (for section 2+) memory."""
    if section_number == 1:
        return f"You are reading section {section_number} of a {genre} manuscript. Lines in this section are numbered {line_start} to {line_end}. Only reference line numbers between {line_start} and {line_end}."
    return f"""Previous memory:
{memory_str}

Lines {line_start}-{line_end}. Section {section_number} of a {genre} manuscript."""


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
    # Cap user message size to avoid provider limits and timeouts (~4k tokens)
    MAX_USER_CHARS = 16000
    if len(numbered_text) > MAX_USER_CHARS:
        numbered_text = numbered_text[:MAX_USER_CHARS] + "\n[... text truncated ...]"
        logger.info(f"[{reader_name}] Section {section_number}: user message capped to {MAX_USER_CHARS} chars")

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
        max_tokens=800,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    chat_plain = make_chat(system_prompt).with_params(max_tokens=800, temperature=temperature)

    READER_LLM_TIMEOUT = 150  # seconds per attempt

    async def _call_llm(use_json_format: bool):
        chat = chat_with_json if use_json_format else chat_plain
        async with _get_llm_semaphore():
            return await asyncio.wait_for(
                chat.send_message(UserMessage(text=f"Section {section_number}:\n\n{numbered_text}")),
                timeout=READER_LLM_TIMEOUT,
            )

    # ── API call with retries for transient failures and rate limits
    logger.info(f"[{reader_name}] Section {section_number}: LLM call started (temp={temperature})")
    t0 = time.monotonic()
    response = None
    last_error = None
    max_attempts = 4  # allow extra retries for rate limit (wait and retry)
    for attempt in range(max_attempts):
        try:
            response = await _call_llm(use_json_format=True)
            break
        except asyncio.TimeoutError as e:
            last_error = e
            elapsed = time.monotonic() - t0
            logger.warning(f"[{reader_name}] Section {section_number}: attempt {attempt + 1} TIMED OUT after {elapsed:.1f}s")
            if attempt == 0:
                await asyncio.sleep(2)  # brief delay before retry
                continue
            raise
        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            # Transient socket error on Windows (non-blocking socket would block)
            is_socket_would_block = (
                isinstance(e, OSError) and getattr(e, "winerror", None) == 10035
            ) or "10035" in str(e)
            if is_socket_would_block:
                wait_sec = 2.0
                logger.warning(
                    f"[{reader_name}] Section {section_number}: transient socket error (WinError 10035), waiting {wait_sec}s then retry (attempt {attempt + 1}/{max_attempts})"
                )
                await asyncio.sleep(wait_sec)
                if attempt < max_attempts - 1:
                    continue
                raise
            # Rate limit: wait suggested time (e.g. "try again in 7.044s") then retry
            is_rate_limit = (
                isinstance(e, getattr(litellm, "RateLimitError", type(None)))
                or "rate limit" in err_str
                or "ratelimit" in err_str
            )
            if is_rate_limit:
                wait_match = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", str(e), re.I)
                wait_sec = min(float(wait_match.group(1)) if wait_match else 10.0, 60.0)
                logger.warning(
                    f"[{reader_name}] Section {section_number}: rate limited, waiting {wait_sec:.1f}s then retry (attempt {attempt + 1}/{max_attempts})"
                )
                await asyncio.sleep(wait_sec)
                if attempt < max_attempts - 1:
                    continue
                raise
            if "response_format" in err_str or "json_schema" in err_str:
                logger.warning(f"[{reader_name}] Section {section_number}: provider may not support json_object, retrying without")
                try:
                    response = await _call_llm(use_json_format=False)
                    break
                except Exception:
                    raise last_error
            logger.warning(f"[{reader_name}] Section {section_number}: attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            raise
    if response is None:
        raise last_error or RuntimeError("No response from LLM")

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

    # ── Save reaction (retry with fresh id on failure to avoid duplicate key on false-negative)
    reaction_doc = None
    for db_attempt in range(2):
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
        try:
            await db.reader_reactions.insert_one({**reaction_doc})
            break
        except Exception as db_err:
            err_str = str(db_err)
            # Duplicate key usually means first attempt succeeded; reuse existing row
            if "23505" in err_str or "duplicate key" in err_str.lower():
                existing = await db.reader_reactions.find_one(
                    {"manuscript_id": manuscript_id, "reader_id": reader["id"], "section_number": section_number},
                    {"_id": 0},
                )
                if existing:
                    reaction_doc = existing
                    logger.info(f"[{reader_name}] Section {section_number}: reaction already present (duplicate key), reusing")
                    break
            logger.warning(f"[{reader_name}] Section {section_number}: reaction insert attempt {db_attempt + 1} failed: {db_err}")
            if db_attempt == 0:
                await asyncio.sleep(1)
                continue
            raise
    if reaction_doc is None:
        raise RuntimeError("Failed to save reaction")
    logger.info(f"[{reader_name}] Section {section_number}: stored to DB")

    # ── Save memory update (retry with fresh id on failure; on duplicate key, skip to avoid double insert)
    if memory_update and isinstance(memory_update, dict):
        for db_attempt in range(2):
            mem_doc = {
                "id": str(uuid.uuid4()),
                "manuscript_id": manuscript_id,
                "reader_id": reader["id"],
                "section_number": section_number,
                "memory_json": memory_update,
                "created_at": now_iso(),
            }
            try:
                await db.reader_memories.insert_one({**mem_doc})
                break
            except Exception as db_err:
                err_str = str(db_err)
                if "23505" in err_str or "duplicate key" in err_str.lower():
                    logger.info(f"[{reader_name}] Section {section_number}: memory already present (duplicate key), skipping insert")
                    break
                logger.warning(f"[{reader_name}] Section {section_number}: memory insert attempt {db_attempt + 1} failed: {db_err}")
                if db_attempt == 0:
                    await asyncio.sleep(1)
                    continue
                raise

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
            "message": f"{reader_name} had an error on this section, moving on",
        })
