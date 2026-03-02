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


VALID_COMMENT_TYPES = (
    "reaction", "prediction", "confusion", "critique", "praise", "theory", "comparison", "callback", "pacing"
)


def _validate_reader_parsed(parsed: Dict, fallback: Dict) -> Dict:
    """Validate and normalize parsed reader response. Drop invalid comments."""
    if not isinstance(parsed, dict):
        return fallback
    out = {
        "inline_comments": [],
        "section_reflection": parsed.get("section_reflection"),
        "memory_update": parsed.get("memory_update") if isinstance(parsed.get("memory_update"), dict) else fallback["memory_update"],
    }
    raw_comments = parsed.get("inline_comments")
    if isinstance(raw_comments, list):
        for c in raw_comments:
            if not isinstance(c, dict):
                continue
            line = c.get("line") is not None and c.get("line") or c.get("paragraph")
            if line is None:
                continue
            try:
                line = int(float(line))
            except (TypeError, ValueError):
                continue
            comment_type = c.get("type")
            if not isinstance(comment_type, str):
                comment_type = "reaction"
            if comment_type not in VALID_COMMENT_TYPES:
                comment_type = "reaction"
            comment_val = c.get("comment")
            if comment_val is not None and not isinstance(comment_val, str):
                comment_val = str(comment_val)
            else:
                comment_val = comment_val or ""
            out["inline_comments"].append({"line": line, "type": comment_type, "comment": comment_val})
    if out["section_reflection"] is not None and not isinstance(out["section_reflection"], str):
        out["section_reflection"] = str(out["section_reflection"])
    return out


def parse_reader_response(raw_text: str, previous_memory: Optional[Dict] = None) -> Dict:
    """
    Parse reader response with aggressive repair. Returns valid dict or fallback.
    Handles markdown fences, preamble, smart quotes, trailing commas, comments, and extracts
    inline_comments/section_reflection when full JSON is broken.
    """
    fallback = {
        "inline_comments": [],
        "section_reflection": "Reader encountered a formatting issue for this section.",
        "memory_update": previous_memory if isinstance(previous_memory, dict) else {},
    }

    if not raw_text or not isinstance(raw_text, str):
        logger.warning("parse_reader_response: empty or non-string input, using fallback")
        fallback["_used_fallback"] = True
        return fallback

    text = raw_text.strip()
    logger.debug("parse_reader_response: raw response length %s chars", len(text))

    # Step 1: Try direct parse
    try:
        parsed = json.loads(text)
        if _parse_validate(parsed):
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

    # Step 3: Fix common JSON issues
    repaired = cleaned
    repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"//.*?\n", "\n", repaired)
    # Fix unescaped newlines inside string values (section_reflection)
    repaired = re.sub(
        r'(?<=": ")([^"]*)\n([^"]*")',
        lambda m: m.group(0).replace("\n", "\\n"),
        repaired,
    )

    try:
        parsed = json.loads(repaired)
        if _parse_validate(parsed):
            logger.info("parse_reader_response: parsed after repair")
            return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # Step 4: Nuclear option — extract inline_comments and section_reflection via regex
    comments_match = re.search(r'"inline_comments"\s*:\s*\[(.+?)\]', repaired, re.DOTALL)
    reflection_match = re.search(r'"section_reflection"\s*:\s*"(.+?)"', repaired, re.DOTALL)

    if comments_match:
        try:
            comments_str = "[" + comments_match.group(1) + "]"
            comments_str = re.sub(r",\s*([}\]])", r"\1", comments_str)
            comments = json.loads(comments_str)
            reflection = None
            if reflection_match:
                reflection = reflection_match.group(1).replace("\\n", " ").strip()
            valid_comments = []
            for c in comments:
                if not isinstance(c, dict):
                    continue
                if "paragraph" not in c and "line" not in c:
                    continue
                if "comment" not in c:
                    continue
                try:
                    p = c.get("paragraph", c.get("line"))
                    int(float(p))
                except (ValueError, TypeError):
                    continue
                line = c.get("line") is not None and c.get("line") or c.get("paragraph")
                try:
                    line = int(float(line))
                except (TypeError, ValueError):
                    continue
                comment_type = c.get("type", "reaction")
                if not isinstance(comment_type, str) or comment_type not in VALID_COMMENT_TYPES:
                    comment_type = "reaction"
                comment_val = c.get("comment")
                comment_val = str(comment_val) if comment_val is not None else ""
                valid_comments.append({"line": line, "type": comment_type, "comment": comment_val})
            logger.info("parse_reader_response: extracted %s comments from broken JSON", len(valid_comments))
            return {
                "inline_comments": valid_comments,
                "section_reflection": reflection,
                "memory_update": previous_memory if isinstance(previous_memory, dict) else {},
            }
        except json.JSONDecodeError:
            pass

    logger.error("parse_reader_response: all parse attempts failed. Raw preview: %s", raw_text[:500])
    fallback["_used_fallback"] = True
    return fallback


def _parse_validate(result: Dict) -> bool:
    """Check that the result has the expected structure."""
    if not isinstance(result, dict):
        return False
    if "inline_comments" not in result:
        return False
    if not isinstance(result["inline_comments"], list):
        return False
    return True


def validate_inline_comments(
    comments: List[Dict], line_start: int, line_end: int
) -> List[Dict]:
    """Clamp out-of-range line numbers to the nearest valid line. Ensure comment is a string for JSONB.
    Accepts "line" or "paragraph" (paragraph is 1-based index; if present we map to line when possible).
    """
    valid = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        line = c.get("line")
        if line is None:
            # v4 may send "paragraph"; we don't have paragraph→line map here, so skip if no line
            para = c.get("paragraph")
            if para is not None:
                try:
                    line = int(float(para))
                    # Treat paragraph as 1-based index; clamp to range (rough mapping)
                    line = max(line_start, min(line_end, line_start + line - 1))
                except (TypeError, ValueError):
                    continue
            else:
                continue
        try:
            line = int(float(line))
        except (TypeError, ValueError):
            continue
        line = max(line_start, min(line_end, line))
        comment_val = c.get("comment")
        if comment_val is not None and not isinstance(comment_val, str):
            comment_val = str(comment_val)
        else:
            comment_val = comment_val or ""
        raw_type = c.get("type", "reaction")
        comment_type = raw_type if isinstance(raw_type, str) and raw_type in VALID_COMMENT_TYPES else "reaction"
        valid.append({
            "line": line,
            "type": comment_type,
            "comment": comment_val,
        })
    return valid
