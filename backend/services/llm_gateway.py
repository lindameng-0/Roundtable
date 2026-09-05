"""Small provider-neutral boundary for structured model calls."""
import json
from dataclasses import dataclass
from typing import Any, Dict

import config as _cfg
from services.model_routing import ModelRoute, UsageRecord, usage_record
from services.reader_memory import count_tokens
from services.cost_control import estimate_cost, release, reserve, settle
from utils import _get_api_key_for_provider, _litellm_model_string, supports_custom_temperature


@dataclass
class StructuredCompletion:
    data: Dict[str, Any]
    usage: UsageRecord
    raw_text: str


def _usage_value(usage: Any, *names: str) -> int:
    for name in names:
        value = getattr(usage, name, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(name)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return 0


async def structured_completion(
    *,
    route: ModelRoute,
    role: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
    max_tokens: int = 2500,
    manuscript_id: str | None = None,
    operation_key: str | None = None,
) -> StructuredCompletion:
    if _cfg.MOCK_LLM:
        raise RuntimeError("Mock structured completions must be supplied by the calling workflow")

    import litellm

    api_key = _get_api_key_for_provider(route.provider)
    if not api_key:
        raise ValueError(f"No API key configured for provider '{route.provider}'")
    kwargs = {
        "model": _litellm_model_string(route.provider, route.model),
        "api_key": api_key,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if temperature is not None and supports_custom_temperature(route.provider, route.model):
        kwargs["temperature"] = temperature
    # Gemini 2.5 Flash defaults to an unbounded/dynamic thinking budget. Those
    # hidden reasoning tokens count against max_tokens and historically cut
    # reader JSON mid-object. Low maps to a bounded 1,024-token budget, which
    # preserves useful deliberation while leaving room for the visible output.
    if route.provider == "gemini" and route.model == "gemini-2.5-flash":
        kwargs["reasoning_effort"] = "low"
    total_input = 0
    total_output = 0
    last_raw = ""
    last_error = None
    reservation_id = None
    if manuscript_id:
        prompt_tokens = count_tokens(system_prompt + user_prompt)
        retry_tokens = min(max(max_tokens * 2, 1200), 16000)
        reserved_cost = estimate_cost(route, prompt_tokens * 2 + 80, max_tokens + retry_tokens)
        if reserved_cost is None:
            raise RuntimeError(f"No cost-control price is configured for {route.key}; refusing an unbudgeted model call")
        reservation_id = await reserve(manuscript_id, role, operation_key or role, reserved_cost)
    try:
        for attempt in range(2):
            call_kwargs = dict(kwargs)
            if attempt:
            # A malformed response usually means the provider spent much of
            # the output allowance on reasoning and cut JSON mid-object. One
            # bounded retry gets a larger ceiling and an explicit repair cue.
            # Preserve large editor budgets. The former 6k ceiling made an
            # editor retry smaller than its first 12k attempt.
                call_kwargs["max_tokens"] = min(max(max_tokens * 2, 1200), 16000)
                call_kwargs["messages"] = [
                    *kwargs["messages"],
                    {
                        "role": "user",
                        "content": "Your previous response was incomplete JSON. Return the complete JSON object only.",
                    },
                ]
            response = await litellm.acompletion(**call_kwargs)
            choice = response.choices[0] if response.choices else None
            raw = choice.message.content if choice and getattr(choice, "message", None) else ""
            usage = getattr(response, "usage", None)
            total_input += _usage_value(usage, "prompt_tokens", "input_tokens") or count_tokens(system_prompt + user_prompt)
            total_output += _usage_value(usage, "completion_tokens", "output_tokens") or count_tokens(raw)
            last_raw = raw or ""
            if not last_raw:
                last_error = RuntimeError(f"{route.key} returned no content")
                continue
            try:
                data = json.loads(last_raw)
                usage_row = usage_record(route, role, total_input, total_output)
                await settle(reservation_id, usage_row.estimated_cost_usd)
                reservation_id = None
                return StructuredCompletion(data, usage_row, last_raw)
            except json.JSONDecodeError as exc:
                last_error = exc
        raise RuntimeError(
            f"{route.key} returned malformed JSON after one repair retry: {last_error}; "
            f"raw preview={last_raw[:160]!r}"
        ) from last_error
    except Exception:
        if total_input or total_output:
            await settle(reservation_id, usage_record(route, role, total_input, total_output).estimated_cost_usd)
        else:
            await release(reservation_id)
        raise
