import asyncio
import sys
from types import SimpleNamespace

import config
from utils import make_chat, UserMessage


def test_legacy_chat_wrapper_also_omits_gpt5_temperature(monkeypatch):
    calls = []

    async def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(acompletion=fake_completion))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    chat = make_chat("system").with_model("openai", "gpt-5.6-luna").with_params(temperature=0.4)
    assert asyncio.run(chat.send_message(UserMessage("hello"))) == "ok"
    assert "temperature" not in calls[0]
