import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app import llm
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        reply = await llm.chat(req.message, req.system)
    except llm.LLMError as e:
        # 502 Bad Gateway：我們的服務沒問題，是上游（LLM）出錯
        raise HTTPException(status_code=502, detail=f"LLM 呼叫失敗：{e}")
    return ChatResponse(reply=reply)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    # 先連上 LLM 再回傳 StreamingResponse：
    # 串流一開始，狀態碼 200 就已經送出，之後出錯就沒辦法改成 502 了
    try:
        chunks = await llm.stream_chat(req.message, req.system)
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 呼叫失敗：{e}")

    async def generate():
        try:
            async for text in chunks:
                yield text
        except llm.LLMError:
            # 串流途中失敗：狀態碼已送出，只能記 log 並告訴使用者回答不完整
            logger.exception("串流途中 LLM 呼叫失敗")
            yield "\n\n[錯誤：LLM 回應中斷]"

    return StreamingResponse(generate(), media_type="text/plain")
