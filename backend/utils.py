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


def make_chat(system_prompt: str, session_id: Optional[str] = None) -> LiteLLMChat:
    """Build a chat client using the current (potentially runtime-changed) model config."""
    chat = LiteLLMChat(system_prompt, session_id=session_id)
    return chat.with_model(_cfg.LLM_PROVIDER, _cfg.LLM_MODEL)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


VALID_COMMENT_TYPES = (
    "reaction", "prediction", "confusion", "critique", "praise", "theory", "comparison", "callback", "pacing"
)


def parse_reader_response(raw_text: str, previous_memory: Optional[Dict] = None) -> Dict:
    """
    Parse and validate reader LLM response JSON. Repairs common malformations.
    Returns dict with inline_comments, section_reflection, memory_update.
    On total failure returns fallback with previous_memory carried forward.
    """
    fallback = {
        "inline_comments": [],
        "section_reflection": "Reader encountered a formatting issue for this section.",
        "memory_update": previous_memory if isinstance(previous_memory, dict) else {},
    }
    if not raw_text or not isinstance(raw_text, str):
        logger.info("parse_reader_response: empty or non-string input, using fallback")
        return fallback

    text = raw_text.strip()
    repaired = False

    # 1) Direct parse
    try:
        parsed = json.loads(text)
        return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # 2) Strip before first { and after last }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
        repaired = True
        try:
            parsed = json.loads(text)
            logger.info("parse_reader_response: parsed after stripping outer text")
            return _validate_reader_parsed(parsed, fallback)
        except json.JSONDecodeError:
            pass

    # 3) Remove markdown code fences
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    # 4) Fix trailing commas before } or ]
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    try:
        parsed = json.loads(text)
        if repaired:
            logger.info("parse_reader_response: parsed after trailing-comma fix")
        return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    # 5) Try "key"= -> "key":
    text_alt = re.sub(r'"(\w+)"\s*=', r'"\1":', text)
    try:
        parsed = json.loads(text_alt)
        logger.info("parse_reader_response: parsed after key= fix")
        return _validate_reader_parsed(parsed, fallback)
    except json.JSONDecodeError:
        pass

    logger.warning("parse_reader_response: all repair attempts failed, using fallback")
    fallback["_used_fallback"] = True
    return fallback


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
