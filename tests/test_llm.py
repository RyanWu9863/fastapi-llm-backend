"""測試 app/llm.py 這層包裝本身：參數組裝、SDK 錯誤轉換。

conftest 的 fake_llm 會把 llm.chat 換掉，所以在模組載入時（fixture 生效前）先拿到真正的函式。
"""

import asyncio
from types import SimpleNamespace

import openai
import pytest

from app import llm
from app.config import settings
from app.llm import chat as real_chat


def test_build_kwargs_omits_optional_params(monkeypatch):
    monkeypatch.setattr(settings, "llm_reasoning_effort", None)
    kwargs = llm._build_kwargs([{"role": "user", "content": "hi"}], "系統提示")

    assert kwargs["messages"] == [
        {"role": "system", "content": "系統提示"},
        {"role": "user", "content": "hi"},
    ]
    # 沒設定的參數不能傳：不是每個模型或服務都支援
    for key in ("reasoning_effort", "response_format", "temperature"):
        assert key not in kwargs


def test_build_kwargs_includes_schema_and_options(monkeypatch):
    monkeypatch.setattr(settings, "llm_reasoning_effort", "none")
    kwargs = llm._build_kwargs([], "系統提示", json_schema={"type": "object"}, temperature=0)

    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert kwargs["temperature"] == 0


def test_chat_returns_content(monkeypatch):
    async def fake_create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="回答"))],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2),
        )

    monkeypatch.setattr(llm._client.chat.completions, "create", fake_create)
    assert asyncio.run(real_chat([], "系統提示")) == "回答"


def test_chat_converts_sdk_error_to_llm_error(monkeypatch):
    async def fake_create(**kwargs):
        raise openai.APIConnectionError(request=None)

    monkeypatch.setattr(llm._client.chat.completions, "create", fake_create)
    # router 只需要認得 LLMError，不必知道底層 SDK 的例外
    with pytest.raises(llm.LLMError):
        asyncio.run(real_chat([], "系統提示"))
