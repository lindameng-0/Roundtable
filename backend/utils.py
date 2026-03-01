import uuid
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


def validate_inline_comments(
    comments: List[Dict], line_start: int, line_end: int
) -> List[Dict]:
    """Clamp out-of-range line numbers to the nearest valid line."""
    valid = []
    for c in comments:
        if not isinstance(c, dict):
            continue
        line = c.get("line")
        if not isinstance(line, int):
            try:
                line = int(line)
            except (TypeError, ValueError):
                continue
        line = max(line_start, min(line_end, line))
        valid.append({
            "line": line,
            "type": c.get("type", "reaction"),
            "comment": c.get("comment", ""),
        })
    return valid
