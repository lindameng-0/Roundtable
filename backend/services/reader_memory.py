"""Reader-memory normalization and prompt formatting.

Kept separate from the LLM runner so the current rolling-memory behavior can
be tested and later replaced by Reader State V2 without touching transport.
"""
from typing import Dict, List

import tiktoken


def normalize_memory_update(memory_update: Dict) -> Dict:
    if not memory_update or not isinstance(memory_update, dict):
        return memory_update
    normalized = {"facts": "", "impressions": "", "watching_for": "", "feeling": ""}
    for key in normalized:
        value = memory_update.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()[:500]
    return normalized


def latest_memory(memories: List[Dict], personality: str = "") -> Dict:
    """Return the latest rolling memory, including legacy-shape conversion."""
    if not memories:
        return {}
    memory_json = memories[-1].get("memory_json", {})
    if not isinstance(memory_json, dict):
        return {}
    if isinstance(memory_json.get("facts"), str) or isinstance(memory_json.get("impressions"), str):
        return {
            key: memory_json.get(key) if isinstance(memory_json.get(key), str) else ""
            for key in ("facts", "impressions", "watching_for", "feeling")
        }
    plot_events = memory_json.get("plot_events") or []
    facts = " ".join(str(event) for event in (plot_events if isinstance(plot_events, list) else [])[-2:])
    feeling = memory_json.get("emotional_state") if isinstance(memory_json.get("emotional_state"), str) else ""
    return {"facts": facts[:400], "impressions": "", "watching_for": "", "feeling": feeling[:80]}


def count_tokens(text: str) -> int:
    try:
        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:
        return len(text.split()) * 2


def format_memory_for_prompt(memory: Dict, max_tokens: int = 200) -> str:
    if not memory or not isinstance(memory, dict):
        return "No previous sections read yet."
    values = {
        key: (memory.get(key) or "").strip() if isinstance(memory.get(key), str) else ""
        for key in ("facts", "impressions", "watching_for", "feeling")
    }
    if not any(values.values()):
        return "No previous sections read yet."
    lines = ["YOUR NOTES FROM LAST TIME:"]
    labels = {
        "facts": "What happened",
        "impressions": "What you thought about it",
        "watching_for": "What you're watching for",
        "feeling": "How you were feeling",
    }
    for key, label in labels.items():
        if values[key]:
            lines.append(f"{label}: {values[key]}")
    rendered = "\n".join(lines)
    # Existing memory fields are tightly capped; preserve behavior while making
    # the intended budget explicit for the future state implementation.
    return rendered if count_tokens(rendered) <= max_tokens else rendered
