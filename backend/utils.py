import uuid
import logging
from datetime import datetime, timezone
from typing import List, Dict

from emergentintegrations.llm.chat import LlmChat, UserMessage
import config as _cfg  # import module so we always read the live (mutable) LLM_MODEL/PROVIDER

logger = logging.getLogger(__name__)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_chat(system_prompt: str, session_id: str = None) -> LlmChat:
    """Build an LlmChat using the current (potentially runtime-changed) model config."""
    sid = session_id or str(uuid.uuid4())
    return LlmChat(
        api_key=_cfg.EMERGENT_LLM_KEY,
        session_id=sid,
        system_message=system_prompt,
    ).with_model(_cfg.LLM_PROVIDER, _cfg.LLM_MODEL)


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
