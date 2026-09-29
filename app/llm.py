from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.config import settings

# 整個 app 共用一個 client：它內部有連線池，每次請求都重建會浪費資源
_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key)

EMBED_BATCH_SIZE = 32


class LLMError(Exception):
    """LLM 呼叫失敗。router 只需要認得這個例外，不必知道底層用哪家 SDK。"""


def _build_kwargs(
    messages: list[dict],
    system: str,
    json_schema: dict | None = None,
    temperature: float | None = None,
) -> dict:
    kwargs = {
        "model": settings.llm_model,
        "max_tokens": 1024,
        "messages": [{"role": "system", "content": system}, *messages],
    }
    # 有設定才傳：不是每個模型或服務都支援這個參數
    if settings.llm_reasoning_effort:
        kwargs["reasoning_effort"] = settings.llm_reasoning_effort
    if json_schema is not None:
        # 結構化輸出：模型生成時就被限制只能產生符合 schema 的 JSON
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": json_schema},
        }
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


async def chat(
    messages: list[dict],
    system: str,
    *,
    json_schema: dict | None = None,
    temperature: float | None = None,
) -> str:
    """messages 是依時間排序的對話（最後一則是這次的提問），等模型完整回答後一次回傳。

    json_schema：要求回傳符合此 schema 的 JSON 字串（呼叫端仍須自行驗證）。
    """
    try:
        resp = await _client.chat.completions.create(
            **_build_kwargs(messages, system, json_schema, temperature)
        )
    except openai.APIError as e:
        raise LLMError(str(e)) from e
    return resp.choices[0].message.content or ""


async def embed(texts: list[str]) -> list[list[float]]:
    """把多段文字轉成向量，順序跟輸入一致；分批送出，避免單一請求太大。"""
    vectors = []
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            resp = await _client.embeddings.create(
                model=settings.embedding_model, input=texts[i : i + EMBED_BATCH_SIZE]
            )
            vectors.extend(d.embedding for d in resp.data)
    except openai.APIError as e:
        raise LLMError(str(e)) from e
    return vectors


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
