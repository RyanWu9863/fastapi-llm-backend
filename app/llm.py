from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.config import settings

# 整個 app 共用一個 client：它內部有連線池，每次請求都重建會浪費資源
_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)


class LLMError(Exception):
    """LLM 呼叫失敗。router 只需要認得這個例外，不必知道底層用哪家 SDK。"""


def _build_kwargs(messages: list[dict], system: str) -> dict:
    kwargs = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "messages": [{"role": "system", "content": system}, *messages],
    }
    # 有設定才傳：不是每個模型或服務都支援這個參數
    if settings.llm_reasoning_effort:
        kwargs["reasoning_effort"] = settings.llm_reasoning_effort
    return kwargs


async def chat(messages: list[dict], system: str) -> str:
    """messages 是依時間排序的對話（最後一則是這次的提問），等模型完整回答後一次回傳。"""
    try:
        resp = await _client.chat.completions.create(**_build_kwargs(messages, system))
    except openai.APIError as e:
        raise LLMError(str(e)) from e
    return resp.choices[0].message.content or ""


async def stream_chat(messages: list[dict], system: str) -> AsyncIterator[str]:
    """先建立連線（失敗會在這裡就丟出 LLMError），再回傳逐段產生文字的 iterator。"""
    try:
        stream = await _client.chat.completions.create(
            **_build_kwargs(messages, system), stream=True
        )
    except openai.APIError as e:
        raise LLMError(str(e)) from e
    return _iter_text(stream)


async def _iter_text(stream) -> AsyncIterator[str]:
    try:
        async for chunk in stream:
            # 有些 chunk 不帶文字（例如最後一個只有結束原因），跳過
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except openai.APIError as e:
        raise LLMError(str(e)) from e
