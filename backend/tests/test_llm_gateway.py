import asyncio
import json
import sys
from types import SimpleNamespace

import config
from services.llm_gateway import structured_completion
from services.model_routing import parse_route


def _response(content, prompt=10, completion=20):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
    )


def test_structured_completion_repairs_truncated_json_once(monkeypatch):
    calls = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return _response('{"reading_journal":"cut', completion=100)
        return _response(json.dumps({"reading_journal": "complete"}), completion=25)

    fake_litellm = SimpleNamespace(acompletion=fake_completion)
    monkeypatch.setitem(sys.modules, "litellm", fake_litellm)
    monkeypatch.setattr(config, "MOCK_LLM", False)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")

    result = asyncio.run(structured_completion(
        route=parse_route("gemini:gemini-2.5-flash"),
        role="reader",
        system_prompt="system",
        user_prompt="user",
        max_tokens=500,
    ))

    assert result.data["reading_journal"] == "complete"
    assert len(calls) == 2
    assert calls[1]["max_tokens"] == 1200
    assert calls[0]["reasoning_effort"] == "low"
    assert result.usage.output_tokens == 125


def test_gpt5_route_omits_unsupported_temperature(monkeypatch):
    calls = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response('{"ok":true}')

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_completion))
    monkeypatch.setattr(config, "MOCK_LLM", False)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")

    result = asyncio.run(structured_completion(
        route=parse_route("openai:gpt-5.6-terra"),
        role="editor",
        system_prompt="system",
        user_prompt="user",
        temperature=0.2,
    ))

    assert result.data == {"ok": True}
    assert "temperature" not in calls[0]


def test_non_gpt5_route_keeps_temperature(monkeypatch):
    calls = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return _response('{"ok":true}')

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_completion))
    monkeypatch.setattr(config, "MOCK_LLM", False)
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "test-key")

    asyncio.run(structured_completion(
        route=parse_route("anthropic:claude-sonnet-5"),
        role="reader",
        system_prompt="system",
        user_prompt="user",
        temperature=0.7,
    ))

    assert calls[0]["temperature"] == 0.7
