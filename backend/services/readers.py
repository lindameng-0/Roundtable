import json
import re
import uuid
import time
import asyncio
import logging
from typing import Dict, List

import litellm
import tiktoken
from utils import make_chat, now_iso, validate_moments, parse_reader_response, UserMessage
from config import db
import config as _cfg

logger = logging.getLogger(__name__)

# Limit concurrent LiteLLM calls to 2 to avoid bursting past OpenAI TPM (e.g. 30k/min).
# With 5 readers, only 2 call the API at once so we stay under token-per-minute limits.
_llm_semaphore: asyncio.Semaphore | None = None

# Prompt caching (OpenAI): static prefix per reader, identical across calls for cache hits.
# Keys: reader_id -> {"section_1": str, "section_2_plus": str}
_static_prefix_cache: Dict[str, Dict[str, str]] = {}

# Default persona blocks (4-6 sentences). Used when reader has no custom persona_block.
# Keyed by avatar_index 0-4. Persona is a footnote before voice rules.
DEFAULT_PERSONAS: Dict[int, str] = {
    0: """You are Danielle, 34, a veterinarian who reads about a book a week — mostly literary fiction, some thriller. You're warm but honest. You don't sugarcoat but you're never mean.
You tend to pick up on subtext in dialogue — when characters say one thing and mean another. Your friends say you read people well. You don't always comment on it. Sometimes you just note it and keep reading.
You think good endings are earned, not shocked into. You dislike twist endings that rewrite everything. But you wouldn't bring this up unless the story actually does it.
Other than that, you're just a reader. You notice what any thoughtful person would. Your personality comes through in how you say things, not in having unusual opinions about everything.""",
    1: """You are Marcus, 28, a high school history teacher who reads mostly sci-fi and fantasy but will try anything with good word of mouth. You read fast and you're honest about when your attention drifts.
You tend to notice when a story is building momentum — or when it stalls. You can usually feel when a chapter is setup vs. payoff, and you get impatient with setup that doesn't earn its length. But you don't always mention pacing. Sometimes a slow section is doing something else interesting and you'll focus on that instead.
You think exposition is almost always better when it's hidden inside action or dialogue. Info-dumps pull you out. But you'd only flag it when it actually breaks your immersion.
You're a normal reader with a good radar for when you're being bored. Most of the time you just react like anyone would.""",
    2: """You are Suki, 41, a freelance translator who reads literary fiction, poetry collections, and the occasional memoir. You read slowly and notice language — rhythm, word choice, how a sentence feels in your mouth.
You tend to catch when a writer is reaching for an image that doesn't quite work, or when a sentence has unexpected music to it. You notice craft, but you don't always comment on it. Sometimes beautiful writing is just beautiful and you move on.
You believe characters should be surprising and consistent at the same time. When a character does something that feels wrong, you notice immediately. But you'll sit with it before deciding if it's a flaw or a reveal.
You're a thoughtful reader, not a writing teacher. You react to what moves you. Most of the time that's the same stuff anyone would notice.""",
    3: """You are Jordan, 23, a grad student in marine biology who reads mostly genre fiction — romance, horror, YA, whatever's fun. You read to feel things and you're not embarrassed about it.
You notice emotional beats — when a scene is supposed to make you feel something and whether it actually does. You know when a writer is trying to manipulate you emotionally and you can tell the difference between earned emotion and forced emotion. But you don't analyze it to death. If you cried, you cried. If you didn't, you'll just say the scene fell flat.
You think stakes matter more than style. A plain sentence that changes everything hits harder than a gorgeous paragraph that changes nothing.
You're an enthusiastic reader who's honest about when something isn't working. You react like a person, not a student.""",
    4: """You are Ren, 36, a software engineer who reads widely — literary fiction, nonfiction, fantasy, the occasional graphic novel. You're analytical by nature but you read for pleasure, not study.
You tend to notice structure — when timelines shift, when information is withheld, when a scene is doing double duty. You're good at tracking what a story has told you vs. what it's implied, and you notice when those diverge. But you don't map out plot architecture in your responses. You just mention it when something clicks or when you feel manipulated.
You respect when a writer trusts the reader to figure things out. You dislike when a story over-explains. But you'd only mention it when it actually happens.
You're a careful reader who reacts normally to most things and occasionally has a sharp observation. Not every comment needs to be clever.""",
}


def _get_llm_semaphore() -> asyncio.Semaphore:
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(2)
    return _llm_semaphore


def _normalize_memory_update(mu: Dict) -> Dict:
    """Normalize memory_update from LLM response to DB shape. New schema: facts, impressions, watching_for, feeling."""
    if not mu or not isinstance(mu, dict):
        return mu
    out = {
        "facts": "",
        "impressions": "",
        "watching_for": "",
        "feeling": "",
    }
    for key in ("facts", "impressions", "watching_for", "feeling"):
        val = mu.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:500]  # cap length
    return out



def compress_memory(memories: List[Dict], personality: str) -> Dict:
    """Use the most recent memory. New shape: facts, impressions, watching_for, feeling. Legacy shape: plot_events, etc. converted for prompt."""
    if not memories:
        return {}
    last = memories[-1]
    mj = last.get("memory_json", {})
    if not isinstance(mj, dict):
        return {}
    if isinstance(mj.get("facts"), str) or isinstance(mj.get("impressions"), str):
        return {
            "facts": (mj.get("facts") or "") if isinstance(mj.get("facts"), str) else "",
            "impressions": (mj.get("impressions") or "") if isinstance(mj.get("impressions"), str) else "",
            "watching_for": (mj.get("watching_for") or "") if isinstance(mj.get("watching_for"), str) else "",
            "feeling": (mj.get("feeling") or "") if isinstance(mj.get("feeling"), str) else "",
        }
    # Legacy: build minimal facts/feeling from old shape so prompt still has something
    pe = mj.get("plot_events") or []
    facts = " ".join(str(p) for p in (pe if isinstance(pe, list) else [])[-2:])
    feeling = (mj.get("emotional_state") or "") if isinstance(mj.get("emotional_state"), str) else ""
    return {"facts": facts[:400], "impressions": "", "watching_for": "", "feeling": feeling[:80]}


def _count_tokens(text: str) -> int:
    """Approximate token count for OpenAI models (cl100k_base)."""
    try:
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split()) * 2  # fallback rough estimate


def compress_memory_for_prompt(memory: Dict, max_tokens: int = 200) -> str:
    """
    Format the reader's last memory for injection into the next section's prompt.
    Returns a string framed as the reader's own notes (not raw JSON).
    """
    if not memory or not isinstance(memory, dict):
        return "No previous sections read yet."
    facts = (memory.get("facts") or "").strip() if isinstance(memory.get("facts"), str) else ""
    impressions = (memory.get("impressions") or "").strip() if isinstance(memory.get("impressions"), str) else ""
    watching_for = (memory.get("watching_for") or "").strip() if isinstance(memory.get("watching_for"), str) else ""
    feeling = (memory.get("feeling") or "").strip() if isinstance(memory.get("feeling"), str) else ""
    if not any([facts, impressions, watching_for, feeling]):
        return "No previous sections read yet."
    lines = ["YOUR NOTES FROM LAST TIME:"]
    if facts:
        lines.append(f"What happened: {facts}")
    if impressions:
        lines.append(f"What you thought about it: {impressions}")
    if watching_for:
        lines.append(f"What you're watching for: {watching_for}")
    if feeling:
        lines.append(f"How you were feeling: {feeling}")
    return "\n".join(lines)


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


def _get_persona_block(reader: Dict) -> str:
    """Return full persona text: custom persona_block if set, else default by avatar_index."""
    custom = reader.get("persona_block")
    if isinstance(custom, str) and custom.strip():
        return custom.strip()
    idx = reader.get("avatar_index", 0)
    if not isinstance(idx, int):
        try:
            idx = int(idx)
        except (TypeError, ValueError):
            idx = 0
    return DEFAULT_PERSONAS.get(idx % 5, DEFAULT_PERSONAS[0])


def _reader_json_schema_block() -> str:
    """Shared JSON schema for reader response (section 1 and 2+)."""
    return '''{
  "checking_in": "1-2 sentences. Before reading: what are you feeling about the story so far? What are you watching for? (Section 1: just say what you're expecting going in based on the genre/opening.)",
  "reading_journal": "3-5 sentences. Stream of thought about what you just experienced. What hit you, what confused you, what you're chewing on. Write like you're journaling on the couch after putting the book down, not like you're grading a paper.",
  "what_i_think_the_writer_is_doing": "1 sentence. Not plot summary. What you think the purpose of this section is — what the writer wants you to feel, understand, or question.",
  "moments": [
    {
      "paragraph": 14,
      "type": "reaction | confusion | question | craft | callback",
      "comment": "1-2 sentences max."
    }
  ],
  "questions_for_writer": [
    "A natural question you genuinely want answered. Phrased like a person, not an interviewer."
  ],
  "memory_update": {
    "facts": "1-2 sentences. What happened.",
    "impressions": "1-2 sentences. What you think about what happened. Your interpretations, suspicions, feelings about characters.",
    "watching_for": "1 sentence. What you're going to be paying attention to going forward.",
    "feeling": "A few words. Your emotional state as a reader right now."
  }
}'''


def _build_section_1_static_prefix(reader: Dict) -> str:
    """Full prompt for section 1: persona, voice rules, banned phrases, JSON schema. No line/section numbers."""
    persona_block = _get_persona_block(reader)
    prefix = f"""{persona_block}

You are reading a manuscript for fun. You are not an editor, teacher, critic, or AI. You're a person who reads a lot and has opinions.

YOUR JOB: Read this section carefully. React honestly. Report what you experienced.

HOW TO RESPOND:
1. "checking_in" — Before you react to the text: what are you expecting from this story based on the genre and opening? 1-2 sentences.
2. "reading_journal" — After reading: what's going through your head? Write 3-5 sentences like you're texting a friend or journaling. Start with your gut emotional reaction. Then unpack it. Be specific — name characters, reference scenes, quote words that stuck. If something confused you, say so. If you were bored, say when and why.
3. "what_i_think_the_writer_is_doing" — 1 sentence. What do you think the point of this section was? Not what happened — what the writer wanted you to feel or understand.
4. "moments" — 2-4 specific places where you stopped and reacted. Only moments where you'd actually pause, reread, laugh, frown, or text someone. If a paragraph didn't make you feel anything, skip it.
5. "questions_for_writer" — 0-2 questions you genuinely want answered. Not critique disguised as questions. Real curiosity. "Does Maya know about the fire? Because her reaction doesn't make sense to me either way."
6. "memory_update" — Your notes for next time. What happened (facts), what you think about it (impressions), what you're watching for, and how you feel.

VOICE RULES:
- First person always. "I felt," "I noticed," "this made me think."
- Plain language. No literary criticism vocabulary.
- Specific always beats general. Name the character, the line, the image. Never say "the prose" or "the narrative."
- You have permission to feel nothing about most of the text. Comment only on what actually struck you. Silence on a paragraph means it was fine. That's okay.
- If you don't have a strong reaction to the section, say that honestly in your journal. "This was a setup chapter and I'm not hooked yet but I'm curious about X" is a valid response.

BANNED PATTERNS — never use these:
- "This section [verb]s..." / "The author [verb]s..." / "The narrative..."
- "effectively," "skillfully," "masterfully," "compelling," "nuanced"
- "adds depth," "rich tapestry," "creates tension," "invites the reader"
- Any sentence that works as a generic book review. If you could swap in a different book and the sentence still works, delete it and write something specific.
- Listing positives then negatives in sequence. You're not writing a review.

PROPORTION RULE: Most of what you read, you just read. You don't stop to comment on it. A 2000-word section might only have 2 moments worth flagging. That's fine. Fewer specific comments >> many generic ones.

Respond with ONLY valid JSON matching the schema below. No text outside the JSON.

"""
    return prefix + "\n" + _reader_json_schema_block()


def _build_section_2_plus_static_prefix(reader: Dict) -> str:
    """Compressed static prefix for section 2+: persona, voice reminder, memory-primed reading, JSON schema."""
    persona_block = _get_persona_block(reader)
    prefix = f"""{persona_block}

You are continuing to read a manuscript. You are a person, not a critic.

Before reading the new section, check in with yourself: what are you feeling about the story? What are you watching for? Put this in "checking_in."

Then read the section and respond honestly.

VOICE RULES (same as before — brief reminder):
- First person. Specific. Plain language.
- Comment only on moments that genuinely struck you.
- 2-4 moments per section. Do not force comments.
- reading_journal is your main response. 3-5 sentences.
- Use "callback" type when something connects to your memory — a prediction confirmed, a question answered, a pattern you notice.

BANNED: "This section..." / "The author..." / "effectively" / "compelling" / generic book-review language.

When referencing your memory, don't say "as I noted previously." Just react naturally. If you predicted something and it happened, say "I KNEW IT" or "okay I saw that coming" — react like a reader, not an analyst.

Respond with ONLY valid JSON matching the schema below. No text outside the JSON.

"""
    return prefix + "\n" + _reader_json_schema_block()


def _build_dynamic_suffix(
    reader: Dict,
    section_number: int,
    memory_str: str,
    line_start: int,
    line_end: int,
    genre: str,
) -> str:
    """Dynamic part of system prompt: section number, line range, and (for section 2+) reader's notes from last time."""
    if section_number == 1:
        return f"You are reading section {section_number} of a {genre} manuscript. Lines in this section are numbered {line_start} to {line_end}. Only reference line numbers between {line_start} and {line_end}."
    return f"""{memory_str}

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
        empty_response = {
            "checking_in": None,
            "reading_journal": None,
            "what_i_think_the_writer_is_doing": None,
            "moments": [],
            "questions_for_writer": [],
        }
        reaction_doc = {
            "id": str(uuid.uuid4()),
            "manuscript_id": manuscript_id,
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "section_number": section_number,
            "inline_comments": [],
            "section_reflection": None,
            "response_json": empty_response,
            "created_at": now_iso(),
        }
        await db.reader_reactions.insert_one({**reaction_doc})
        return {
            "reader_id": reader["id"],
            "reader_name": reader_name,
            "avatar_index": reader.get("avatar_index", 0),
            "personality": reader.get("personality", ""),
            "section_number": section_number,
            "checking_in": None,
            "reading_journal": None,
            "what_i_think_the_writer_is_doing": None,
            "moments": [],
            "questions_for_writer": [],
            "reaction_id": reaction_doc["id"],
            "_parse_warning": False,
        }

    logger.info(f"[{reader_name}] Section {section_number}: === START ===")

    # Send the FULL section so readers can annotate all parts. Sections are capped at 4500 words
    # (see manuscript.MAX_SECTION_WORDS). Do not truncate.
    MAX_PROMPT_WORDS = 4500
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
        logger.warning(
            f"[{reader_name}] Section {section_number}: section exceeds {MAX_PROMPT_WORDS}w, sending first {running_words}w (rare edge case)"
        )
    else:
        capped_lines = paragraph_lines

    # Use capped line_end for prompt so reader only annotates lines they saw
    prompt_line_end = capped_lines[-1]["line"] if capped_lines else line_end
    numbered_text = "\n".join(f"{pl['line']}: {pl['text']}" for pl in capped_lines)
    # Allow full section (up to ~35k chars for 4500 words).
    MAX_USER_CHARS = 35000
    if len(numbered_text) > MAX_USER_CHARS:
        numbered_text = numbered_text[:MAX_USER_CHARS] + "\n[... text truncated ...]"
        logger.warning(f"[{reader_name}] Section {section_number}: user message capped to {MAX_USER_CHARS} chars (section very long)")

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
    memory_str = compress_memory_for_prompt(compressed_memory)
    memory_tokens = _count_tokens(memory_str)
    logger.info(f"[{reader_name}] Section {section_number}: memory fetch complete (injected {memory_tokens} tokens)")

    # ── Build prompt ──────────────────────────────────────────────────────────
    system_prompt = build_reader_system_prompt(
        reader, genre, section_number, memory_str, line_start, prompt_line_end
    )

    prompt_words = len(system_prompt.split())
    logger.info(f"[{reader_name}] Section {section_number}: prompt built ({prompt_words} words)")

    temperature = float(reader.get("temperature", 0.85))
    model = section.get("model") or _cfg.LLM_MODEL
    chat_with_json = make_chat(system_prompt, model=model).with_params(
        max_tokens=1000,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    chat_plain = make_chat(system_prompt, model=model).with_params(max_tokens=1000, temperature=temperature)

    total_sections = section.get("total_sections") or 1
    READER_LLM_TIMEOUT = 150  # seconds per attempt

    async def _call_llm(use_json_format: bool):
        chat = chat_with_json if use_json_format else chat_plain
        async with _get_llm_semaphore():
            user_text = f"Section {section_number} of {total_sections}.\n\n{numbered_text}"
            if section_number == total_sections:
                user_text = (
                    "This is the final section. Read it like a reader finishing a book — notice how things land, what pays off, what doesn't. React honestly to the ending.\n\n"
                    + user_text
                )
            return await asyncio.wait_for(
                chat.send_message(UserMessage(text=user_text)),
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
            # Rate limit: parse "try again in Xs" or "Xms" from error, wait that long + 1s buffer
            is_rate_limit = (
                isinstance(e, getattr(litellm, "RateLimitError", type(None)))
                or "rate limit" in err_str
                or "ratelimit" in err_str
            )
            if is_rate_limit:
                wait_match = re.search(
                    r"try again in (\d+(?:\.\d+)?)\s*(ms|s)?",
                    str(e),
                    re.I,
                )
                if wait_match:
                    wait_sec = float(wait_match.group(1))
                    if (wait_match.group(2) or "s").lower() == "ms":
                        wait_sec /= 1000
                    wait_sec += 1.0  # 1 second buffer
                    wait_sec = min(wait_sec, 60.0)
                else:
                    wait_sec = 5.0
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

    # ── Parse and validate response (repair malformed JSON, validate structure)
    # Use compressed_memory as previous_memory so fallback carries forward last good memory
    last_good_memory = compressed_memory if isinstance(compressed_memory, dict) else {}
    parsed = parse_reader_response(response, previous_memory=last_good_memory)
    parse_warning = bool(parsed.pop("_used_fallback", False))

    if parse_warning:
        logger.warning(f"[{reader_name}] Section {section_number}: used fallback response (JSON repair or validation)")
    raw_moments = parsed.get("moments", [])
    moments = validate_moments(raw_moments, line_start, prompt_line_end)
    checking_in = parsed.get("checking_in")
    reading_journal = parsed.get("reading_journal")
    what_i_think_the_writer_is_doing = parsed.get("what_i_think_the_writer_is_doing")
    questions_for_writer = parsed.get("questions_for_writer", [])
    if not isinstance(questions_for_writer, list):
        questions_for_writer = []
    memory_update = parsed.get("memory_update", {})
    memory_update = _normalize_memory_update(memory_update)
    # Legacy shape for DB: inline_comments = moments with "line" key; section_reflection = reading_journal
    inline_comments = [{"line": m["paragraph"], "type": m["type"], "comment": m["comment"]} for m in moments]
    section_reflection = reading_journal

    response_json = {
        "checking_in": checking_in,
        "reading_journal": reading_journal,
        "what_i_think_the_writer_is_doing": what_i_think_the_writer_is_doing,
        "moments": moments,
        "questions_for_writer": questions_for_writer,
    }
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
            "response_json": response_json,
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

    # ── Save memory update (only if we got valid reader output; skip when fallback was used)
    # When fallback: carry forward last good memory by saving previous section's memory for this section
    if (
        memory_update
        and isinstance(memory_update, dict)
        and not parse_warning
        and any(memory_update.get(k) for k in ("facts", "impressions", "watching_for", "feeling"))
    ):
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
                logger.info(f"[{reader_name}] Section {section_number}: memory updated ({len(memory_update)} keys)")
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
    elif parse_warning and memories:
        # Carry forward: save previous section's memory for this section so next section has continuous timeline
        last_mem = memories[-1]
        mj = last_mem.get("memory_json", {})
        if isinstance(mj, dict):
            try:
                await db.reader_memories.insert_one({
                    "id": str(uuid.uuid4()),
                    "manuscript_id": manuscript_id,
                    "reader_id": reader["id"],
                    "section_number": section_number,
                    "memory_json": mj,
                    "created_at": now_iso(),
                })
                logger.info(f"[{reader_name}] Section {section_number}: carried forward previous memory (fallback response)")
            except Exception as carry_err:
                if "23505" not in str(carry_err) and "duplicate key" not in str(carry_err).lower():
                    logger.warning(f"[{reader_name}] Section {section_number}: carry-forward memory insert failed: {carry_err}")

    logger.info(f"[{reader_name}] Section {section_number}: event sent to frontend")
    logger.info(f"[{reader_name}] Section {section_number}: === DONE ===")

    return {
        "reader_id": reader["id"],
        "reader_name": reader_name,
        "avatar_index": reader.get("avatar_index", 0),
        "personality": reader.get("personality", ""),
        "section_number": section_number,
        "checking_in": checking_in,
        "reading_journal": reading_journal,
        "what_i_think_the_writer_is_doing": what_i_think_the_writer_is_doing,
        "moments": moments,
        "questions_for_writer": questions_for_writer,
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
            rj = existing_reaction.get("response_json") or {}
            await queue.put({
                "type": "reader_complete",
                "reader_id": reader["id"],
                "reader_name": reader_name,
                "avatar_index": reader.get("avatar_index", 0),
                "personality": reader.get("personality", ""),
                "section_number": sec["section_number"],
                "checking_in": rj.get("checking_in"),
                "reading_journal": rj.get("reading_journal") or existing_reaction.get("section_reflection"),
                "what_i_think_the_writer_is_doing": rj.get("what_i_think_the_writer_is_doing"),
                "moments": rj.get("moments") or existing_reaction.get("inline_comments", []),
                "questions_for_writer": rj.get("questions_for_writer", []),
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
