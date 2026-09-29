import logging
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app import llm
from app.db import DbSession
from app.models import ChatSession, Message
from app.schemas import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# 只帶最近 20 則訊息（約 10 輪）給 LLM：對話越長越慢、越貴，也可能超過模型的 context 上限
MAX_HISTORY = 20


async def _load_history(db: DbSession, session_id: str | None) -> tuple[str, bool, list[dict]]:
    """回傳 (session_id, 是否為新對話, 歷史訊息)。帶了不存在的 session_id 就回 404。"""
    if session_id is None:
        # 新對話先只產生 id，等 LLM 成功回答後才寫進 DB
        return str(uuid.uuid4()), True, []
    if await db.get(ChatSession, session_id) is None:
        raise HTTPException(status_code=404, detail="找不到這個 session")
    rows = await db.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(MAX_HISTORY)
    )
    # 為了取「最近」N 則而倒序查，送給 LLM 前要轉回時間順序
    history = [{"role": m.role, "content": m.content} for m in reversed(rows.all())]
    return session_id, False, history


async def _save_turn(db: DbSession, session_id: str, is_new: bool, question: str, answer: str):
    """一問一答放在同一個 transaction 一起存：不會只存到問題、沒存到回答。"""
    if is_new:
        db.add(ChatSession(id=session_id))
    db.add_all([
        Message(session_id=session_id, role="user", content=question),
        Message(session_id=session_id, role="assistant", content=answer),
    ])
    await db.commit()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: DbSession):
    session_id, is_new, history = await _load_history(db, req.session_id)
    messages = [*history, {"role": "user", "content": req.message}]
    try:
        reply = await llm.chat(messages, req.system)
    except llm.LLMError as e:
        # 502 Bad Gateway：我們的服務沒問題，是上游（LLM）出錯；這一輪不寫入 DB
        raise HTTPException(status_code=502, detail=f"LLM 呼叫失敗：{e}")
    await _save_turn(db, session_id, is_new, req.message, reply)
    return ChatResponse(session_id=session_id, reply=reply)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, db: DbSession):
    session_id, is_new, history = await _load_history(db, req.session_id)
    messages = [*history, {"role": "user", "content": req.message}]
    # 先連上 LLM 再回傳 StreamingResponse：
    # 串流一開始，狀態碼 200 就已經送出，之後出錯就沒辦法改成 502 了
    try:
        chunks = await llm.stream_chat(messages, req.system)
    except llm.LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM 呼叫失敗：{e}")

    async def generate():
        parts = []
        try:
            async for text in chunks:
                parts.append(text)
                yield text
        except llm.LLMError:
            # 串流途中失敗：狀態碼已送出，只能記 log 並告訴使用者回答不完整
            logger.exception("串流途中 LLM 呼叫失敗")
            yield "\n\n[錯誤：LLM 回應中斷]"
            return  # 回答不完整，這一輪不存
        # 整段回答送完才存；db 能用到這裡是因為 DbSession 設了 scope="request"
        await _save_turn(db, session_id, is_new, req.message, "".join(parts))

    # 串流的 body 是純文字，session_id 改放在 response header
    return StreamingResponse(
        generate(), media_type="text/plain", headers={"X-Session-Id": session_id}
    )
