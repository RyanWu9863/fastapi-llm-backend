from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.db import DbSession
from app.models import ChatSession, Message
from app.schemas import MessageOut

router = APIRouter(tags=["sessions"])


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
async def list_messages(session_id: str, db: DbSession):
    if await db.get(ChatSession, session_id) is None:
        raise HTTPException(status_code=404, detail="找不到這個 session")
    rows = await db.scalars(
        select(Message).where(Message.session_id == session_id).order_by(Message.id)
    )
    # 直接回傳 ORM 物件，FastAPI 會依 response_model 轉成 MessageOut
    return rows.all()
