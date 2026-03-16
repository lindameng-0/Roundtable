import uuid
import json
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

import litellm
import config as _cfg  # import module so we always read the live (mutable) LLM_MODEL/PROVIDER

logger = logging.getLogger(__name__)


class UserMessage:
    """Simple user message for LLM calls (replaces emergentintegrations.llm.chat.UserMessage)."""
    def __init__(self, text: str):
        self.text = text


def _get_api_key_for_provider(provider: str) -> Optional[str]:
    if provider == "openai":
        return _cfg.OPENAI_API_KEY
    if provider == "anthropic":
        return _cfg.ANTHROPIC_API_KEY
    if provider == "gemini":
        return _cfg.GEMINI_API_KEY
    return None


def _litellm_model_string(provider: str, model: str) -> str:
    """LiteLLM expects provider/model for routing (e.g. openai/gpt-4o)."""
    return f"{provider}/{model}"


class LiteLLMChat:
    """Thin wrapper around LiteLLM to match the previous make_chat/send_message interface."""

    def __init__(self, system_prompt: str, session_id: Optional[str] = None):
        self._system_prompt = system_prompt
        self._session_id = session_id or str(uuid.uuid4())
        self._max_tokens: Optional[int] = None
        self._temperature: Optional[float] = None
        self._response_format: Optional[Dict[str, Any]] = None

    def with_model(self, provider: str, model: str) -> "LiteLLMChat":
        self._provider = provider
        self._model = model
        return self

    def with_params(
        self,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> "LiteLLMChat":
        if max_tokens is not None:
            self._max_tokens = max_tokens
        if temperature is not None:
            self._temperature = temperature
        if response_format is not None:
            self._response_format = response_format
        return self

    async def send_message(self, user_message: UserMessage) -> str:
        provider = getattr(self, "_provider", _cfg.LLM_PROVIDER)
        model = getattr(self, "_model", _cfg.LLM_MODEL)
        model_str = _litellm_model_string(provider, model)
        api_key = _get_api_key_for_provider(provider)
        if not api_key:
            raise ValueError(
                f"No API key configured for provider '{provider}'. "
                f"Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY in backend/.env"
            )
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message.text},
        ]
        kwargs: Dict[str, Any] = {
            "model": model_str,
            "messages": messages,
            "api_key": api_key,
        }
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        if self._temperature is not None:
            kwargs["temperature"] = self._temperature
        if self._response_format is not None:
            kwargs["response_format"] = self._response_format
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as e:
            logger.exception("LiteLLM completion failed for %s", model_str)
            raise
        choice = response.choices[0] if response.choices else None
        if not choice or not getattr(choice, "message", None):
            raise RuntimeError("LiteLLM returned no message content")
        return choice.message.content or ""


def make_chat(system_prompt: str, session_id: Optional[str] = None, model: Optional[str] = None) -> LiteLLMChat:
    """Build a chat client. If model is provided (e.g. from manuscript), use it; else use config."""
    chat = LiteLLMChat(system_prompt, session_id=session_id)
    return chat.with_model(_cfg.LLM_PROVIDER, model or _cfg.LLM_MODEL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# New schema: reaction | confusion | question | craft | callback (no praise/critique/prediction/theory/comparison/pacing)
VALID_MOMENT_TYPES = ("reaction", "confusion", "question", "craft", "callback")
# Legacy alias for any code still using old type names
VALID_COMMENT_TYPES = VALID_MOMENT_TYPES


def _normalize_memory_update_parsed(mu: Any) -> Dict:
    """Ensure memory_update has facts, impressions, watching_for, feeling."""
    if not isinstance(mu, dict):
        return {}
    out = {"facts": "", "impressions": "", "watching_for": "", "feeling": ""}
    for key in out:
        val = mu.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()
    return out


def _escape_newlines_in_json_strings(s: str) -> str:
    """Escape literal newlines inside double-quoted JSON string values so json.loads can parse."""
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(s):
        c = s[i]
        if escape_next:
            result.append(c)
            escape_next = False
            i += 1
            continue
        if c == "\\" and in_string:
            result.append(c)
            escape_next = True
            i += 1
            continue
        if c == '"':
            in_string = not in_string
            result.append(c)
            i += 1
            continue
        if in_string and c == "\n":
            result.append("\\n")
            i += 1
            continue
        if in_string and c == "\r":
            result.append("\\r")
            i += 1
            continue
        result.append(c)
        i += 1
    return "".join(result)


def _validate_reader_parsed(parsed: Dict, fallback: Dict) -> Dict:
    """Validate and normalize parsed reader response. New schema: checking_in, reading_journal, what_i_think_the_writer_is_doing, moments, questions_for_writer, memory_update."""
    if not isinstance(parsed, dict):
        return fallback
    # Prefer new keys; accept legacy inline_comments/section_reflection for backward compat
    raw_moments = parsed.get("moments")
    if not isinstance(raw_moments, list):
        raw_moments = parsed.get("inline_comments") or []
    moments = []
    for c in raw_moments:
        if not isinstance(c, dict):
            continue
        para = c.get("paragraph") is not None and c.get("paragraph") or c.get("line")
        if para is None:
            continue
        try:
            para = int(float(para))
        except (TypeError, ValueError):
            continue
        comment_type = c.get("type")
        if not isinstance(comment_type, str) or comment_type not in VALID_MOMENT_TYPES:
            comment_type = "reaction"
        comment_val = c.get("comment")
        if comment_val is not None and not isinstance(comment_val, str):
            comment_val = str(comment_val)
        else:
            comment_val = comment_val or ""
        moments.append({"paragraph": para, "type": comment_type, "comment": comment_val})
    reading_journal = parsed.get("reading_journal")
    if reading_journal is not None and not isinstance(reading_journal, str):
        reading_journal = str(reading_journal)
    if reading_journal is None:
        reading_journal = parsed.get("section_reflection")
    if reading_journal is not None and not isinstance(reading_journal, str):
        reading_journal = str(reading_journal)
    checking_in = parsed.get("checking_in")
    if checking_in is not None and not isinstance(checking_in, str):
        checking_in = str(checking_in) if checking_in else None
    what_doing = parsed.get("what_i_think_the_writer_is_doing")
    if what_doing is not None and not isinstance(what_doing, str):
        what_doing = str(what_doing) if what_doing else None
    qfw = parsed.get("questions_for_writer")
    if isinstance(qfw, list):
        questions_for_writer = [str(q).strip() for q in qfw if q and str(q).strip()]
    else:
        questions_for_writer = []
    memory_update = _normalize_memory_update_parsed(
        parsed.get("memory_update") if isinstance(parsed.get("memory_update"), dict) else fallback.get("memory_update", {})
    )
    return {
        "checking_in": checking_in,
        "reading_journal": reading_journal,
        "what_i_think_the_writer_is_doing": what_doing,
        "moments": moments,
        "questions_for_writer": questions_for_writer,
        "memory_update": memory_update,
    }


def parse_reader_response(raw_text: str, previous_memory: Optional[Dict] = None) -> Dict:
    """
    Parse reader response with aggressive repair. Returns valid dict or fallback.
    Schema: checking_in (nullable), reading_journal, what_i_think_the_writer_is_doing, moments, questions_for_writer, memory_update.
    Tolerance: empty questions_for_writer → []; missing checking_in → null; fewer than 2 moments accepted (no retry).
    Handles markdown fences (strip ```json and ```); Gemini with response_mime_type=application/json should return valid JSON.
    """
    fallback = {
        "checking_in": None,
        "reading_journal": "Reader encountered a formatting issue for this section.",
        "what_i_think_the_writer_is_doing": None,
        "moments": [],
        "questions_for_writer": [],
        "memory_update": _normalize_memory_update_parsed(previous_memory) if isinstance(previous_memory, dict) else {"facts": "", "impressions": "", "watching_for": "", "feeling": ""},
    }

    if not raw_text or not isinstance(raw_text, str):
        logger.warning("parse_reader_response: empty or non-string input, using fallback")
        fallback["_used_fallback"] = True
        return fallback

    text = raw_text.strip()
    logger.debug("parse_reader_response: raw response length %s chars", len(text))

    # Step 1: Try direct parse (then with newlines escaped — Gemini often returns literal newlines in strings)
    try:
        parsed = json.loads(text)
        if _parse_validate(parsed):
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass
    try:
        text_escaped = _escape_newlines_in_json_strings(text)
        parsed = json.loads(text_escaped)
        if _parse_validate(parsed):
            logger.info("parse_reader_response: parsed after escaping newlines (raw)")
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # Step 2: Strip markdown fences and preamble
    cleaned = text
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned.strip())
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        cleaned = cleaned[first_brace : last_brace + 1]

    try:
        parsed = json.loads(cleaned)
        if _parse_validate(parsed):
            logger.info("parse_reader_response: parsed after stripping preamble/fences")
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # Step 2b: Gemini often returns literal newlines inside string values; escape them so JSON is valid
    cleaned_escaped = _escape_newlines_in_json_strings(cleaned)
    try:
        parsed = json.loads(cleaned_escaped)
        if _parse_validate(parsed):
            logger.info("parse_reader_response: parsed after escaping newlines in strings")
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # Step 3: Fix other common JSON issues
    repaired = cleaned_escaped
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"//.*?\n", "\n", repaired)

    try:
        parsed = json.loads(repaired)
        if _parse_validate(parsed):
            logger.info("parse_reader_response: parsed after repair")
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # Step 3.5: Truncated JSON recovery — Gemini sometimes returns incomplete JSON; extract string fields we can
    def _extract_string_field(js: str, key: str) -> Optional[str]:
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"', js)
        if m:
            return m.group(1).replace("\\n", "\n").replace("\\\"", '"').strip()
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"(.*)$', js, re.DOTALL)
        if m:
            return m.group(1).replace("\\n", "\n").replace("\\\"", '"').strip()
        return None
    checking_in = _extract_string_field(repaired, "checking_in")
    reading_journal = _extract_string_field(repaired, "reading_journal") or _extract_string_field(repaired, "section_reflection")
    what_doing = _extract_string_field(repaired, "what_i_think_the_writer_is_doing")
    # Try to extract moments array so we don't lose them when full parse fails (e.g. newlines in strings)
    recovered_moments: List[Dict] = []
    for array_key in ("moments", "inline_comments"):
        mom_match = re.search(r'"' + re.escape(array_key) + r'"\s*:\s*\[', repaired)
        if not mom_match:
            continue
        start = mom_match.end() - 1  # include the [
        depth = 0
        end = -1
        for i in range(start, len(repaired)):
            if repaired[i] == "[":
                depth += 1
            elif repaired[i] == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > start:
            try:
                arr_str = repaired[start:end]
                arr_str = re.sub(r",\s*([}\]])", r"\1", arr_str)
                comments = json.loads(arr_str)
                for c in comments:
                    if not isinstance(c, dict):
                        continue
                    para = c.get("paragraph") or c.get("line")
                    if para is None:
                        continue
                    try:
                        para = int(float(para))
                    except (TypeError, ValueError):
                        continue
                    ct = c.get("type", "reaction")
                    if not isinstance(ct, str) or ct not in VALID_MOMENT_TYPES:
                        ct = "reaction"
                    comment_val = c.get("comment")
                    comment_val = str(comment_val).strip() if comment_val else ""
                    recovered_moments.append({"paragraph": para, "type": ct, "comment": comment_val})
            except (json.JSONDecodeError, ValueError):
                pass
            break
    if reading_journal or checking_in:
        logger.info("parse_reader_response: recovered from truncated JSON (checking_in/reading_journal)%s", f", {len(recovered_moments)} moments" if recovered_moments else "")
        return {
            "checking_in": checking_in,
            "reading_journal": reading_journal or "Reader response was truncated; partial content recovered.",
            "what_i_think_the_writer_is_doing": what_doing,
            "moments": recovered_moments,
            "questions_for_writer": [],
            "memory_update": _normalize_memory_update_parsed(previous_memory) if isinstance(previous_memory, dict) else {"facts": "", "impressions": "", "watching_for": "", "feeling": ""},
        }

    # Step 4: Nuclear option — extract moments or inline_comments and reading_journal via regex
    moments_match = re.search(r'"moments"\s*:\s*\[(.+?)\]', repaired, re.DOTALL)
    if not moments_match:
        moments_match = re.search(r'"inline_comments"\s*:\s*\[(.+?)\]', repaired, re.DOTALL)
    # Match reading_journal value; may contain \n (already escaped) so use non-greedy until ", then allow \"
    reflection_match = re.search(r'"reading_journal"\s*:\s*"((?:[^"\\]|\\.)*)"', repaired)
    if not reflection_match:
        reflection_match = re.search(r'"section_reflection"\s*:\s*"((?:[^"\\]|\\.)*)"', repaired)

    if moments_match:
        try:
            comments_str = "[" + moments_match.group(1) + "]"
            comments_str = re.sub(r",\s*([}\]])", r"\1", comments_str)
            comments = json.loads(comments_str)
            reflection = None
            if reflection_match:
                reflection = reflection_match.group(1).replace("\\n", " ").strip()
            valid_moments = []
            for c in comments:
                if not isinstance(c, dict):
                    continue
                if "paragraph" not in c and "line" not in c:
                    continue
                if "comment" not in c:
                    continue
                try:
                    p = c.get("paragraph", c.get("line"))
                    para = int(float(p))
                except (ValueError, TypeError):
                    continue
                comment_type = c.get("type", "reaction")
                if not isinstance(comment_type, str) or comment_type not in VALID_MOMENT_TYPES:
                    comment_type = "reaction"
                comment_val = c.get("comment")
                comment_val = str(comment_val) if comment_val is not None else ""
                valid_moments.append({"paragraph": para, "type": comment_type, "comment": comment_val})
            logger.info("parse_reader_response: extracted %s moments from broken JSON", len(valid_moments))
            return {
                "checking_in": None,
                "reading_journal": reflection,
                "what_i_think_the_writer_is_doing": None,
                "moments": valid_moments,
                "questions_for_writer": [],
                "memory_update": _normalize_memory_update_parsed(previous_memory) if isinstance(previous_memory, dict) else {"facts": "", "impressions": "", "watching_for": "", "feeling": ""},
            }
        except json.JSONDecodeError:
            pass

    logger.error("parse_reader_response: all parse attempts failed. Raw preview: %s", raw_text[:500])
    fallback["_used_fallback"] = True
    return fallback


def _parse_validate(result: Dict) -> bool:
    """Accept if we have moments (list), inline_comments (list), or reading_journal/section_reflection (str)."""
    if not isinstance(result, dict):
        return False
    if "moments" in result and isinstance(result["moments"], list):
        return True
    if "inline_comments" in result and isinstance(result["inline_comments"], list):
        return True
    if "reading_journal" in result and isinstance(result["reading_journal"], str):
        return True
    if "section_reflection" in result and isinstance(result["section_reflection"], str):
        return True
    return False


def validate_moments(
    moments: List[Dict], line_start: int, line_end: int
) -> List[Dict]:
    """Clamp paragraph numbers to valid range. Ensure type is one of VALID_MOMENT_TYPES. Return list of {paragraph, type, comment}."""
    valid = []
    for c in moments:
        if not isinstance(c, dict):
            continue
        para = c.get("paragraph") is not None and c.get("paragraph") or c.get("line")
        if para is None:
            continue
        try:
            para = int(float(para))
        except (TypeError, ValueError):
            continue
        para = max(line_start, min(line_end, para))
        comment_val = c.get("comment")
        if comment_val is not None and not isinstance(comment_val, str):
            comment_val = str(comment_val)
        else:
            comment_val = comment_val or ""
        raw_type = c.get("type", "reaction")
        comment_type = raw_type if isinstance(raw_type, str) and raw_type in VALID_MOMENT_TYPES else "reaction"
        valid.append({"paragraph": para, "type": comment_type, "comment": comment_val})
    return valid


def validate_inline_comments(
    comments: List[Dict], line_start: int, line_end: int
) -> List[Dict]:
    """Legacy: same as validate_moments but returns items with "line" key for backward compat. Prefer validate_moments."""
    validated = validate_moments(comments, line_start, line_end)
    return [{"line": m["paragraph"], "type": m["type"], "comment": m["comment"]} for m in validated]
