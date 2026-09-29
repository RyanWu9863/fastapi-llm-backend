import logging
import time
from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# 整個 app 共用一個 client：它內部有連線池，每次請求都重建會浪費資源
_client = AsyncOpenAI(
    base_url=settings.llm_base_url,
    api_key=settings.llm_api_key,
    # SDK 預設讀取逾時是 600 秒，太久了；連線逾時設短，LLM 服務掛掉時才能快點失敗
    timeout=openai.Timeout(settings.llm_timeout, connect=5.0),
    # 只重試「可能是暫時性」的錯誤（連線失敗、逾時、429、5xx），400/401/404 重試也沒用，不會重試
    max_retries=settings.llm_max_retries,
)

EMBED_BATCH_SIZE = 32


class LLMError(Exception):
    """LLM 呼叫失敗。router 只需要認得這個例外，不必知道底層用哪家 SDK。"""


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _usage_fields(usage) -> dict:
    """token 用量是 LLM 成本的主要來源，每次呼叫都記下來才能追蹤花費。"""
    if usage is None:
        return {}
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": getattr(usage, "completion_tokens", None),
    }


def _log_error(event: str, start: float, e: openai.APIError) -> None:
    # 只記錯誤類型和狀態碼，不記完整訊息：有些服務的錯誤訊息會帶出部分 API key
    logger.warning(
        f"{event}_failed",
        extra={"fields": {
            "duration_ms": _ms(start),
            "error": type(e).__name__,
            "status_code": getattr(e, "status_code", None),
        }},
    )


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
    start = time.perf_counter()
    try:
        resp = await _client.chat.completions.create(
            **_build_kwargs(messages, system, json_schema, temperature)
        )
    except openai.APIError as e:
        _log_error("llm_chat", start, e)
        raise LLMError(str(e)) from e
    logger.info(
        "llm_chat",
        extra={"fields": {
            "model": settings.llm_model, "duration_ms": _ms(start), **_usage_fields(resp.usage)
        }},
    )
    return resp.choices[0].message.content or ""


async def embed(texts: list[str]) -> list[list[float]]:
    """把多段文字轉成向量，順序跟輸入一致；分批送出，避免單一請求太大。"""
    start = time.perf_counter()
    vectors = []
    prompt_tokens = 0
    try:
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            resp = await _client.embeddings.create(
                model=settings.embedding_model, input=texts[i : i + EMBED_BATCH_SIZE]
            )
            vectors.extend(d.embedding for d in resp.data)
            prompt_tokens += resp.usage.prompt_tokens if resp.usage else 0
    except openai.APIError as e:
        _log_error("llm_embed", start, e)
        raise LLMError(str(e)) from e
    logger.info(
        "llm_embed",
        extra={"fields": {
            "model": settings.embedding_model,
            "texts": len(texts),
            "duration_ms": _ms(start),
            "prompt_tokens": prompt_tokens,
        }},
    )
    return vectors


async def stream_chat(messages: list[dict], system: str) -> AsyncIterator[str]:
    """先建立連線（失敗會在這裡就丟出 LLMError），再回傳逐段產生文字的 iterator。"""
    start = time.perf_counter()
    try:
        stream = await _client.chat.completions.create(
            **_build_kwargs(messages, system),
            stream=True,
            # 串流預設不回 token 用量；開了之後最後一塊會帶 usage
            stream_options={"include_usage": True},
        )
    except openai.APIError as e:
        _log_error("llm_stream", start, e)
        raise LLMError(str(e)) from e
    return _iter_text(stream, start)


async def _iter_text(stream, start: float) -> AsyncIterator[str]:
    first_token_ms = None
    usage = None
    try:
        async for chunk in stream:
            if chunk.usage:
                usage = chunk.usage  # 最後一塊只有 token 用量，沒有文字
            # 有些 chunk 不帶文字（例如只有結束原因），跳過
            if chunk.choices and chunk.choices[0].delta.content:
                if first_token_ms is None:
                    first_token_ms = _ms(start)
                yield chunk.choices[0].delta.content
    except openai.APIError as e:
        _log_error("llm_stream", start, e)
        raise LLMError(str(e)) from e
    logger.info(
        "llm_stream",
        extra={"fields": {
            "model": settings.llm_model,
            # 首字延遲（TTFT）：使用者多久看到第一個字，是串流體驗最重要的指標
            "first_token_ms": first_token_ms,
            "duration_ms": _ms(start),
            **_usage_fields(usage),
        }},
    )
