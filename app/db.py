from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# 用 async 引擎：DB 查詢等待期間不會卡住 event loop，其他請求照樣能處理
engine = create_async_engine(settings.database_url)
# expire_on_commit=False：commit 後物件屬性保留，
# 否則再讀屬性會觸發重新查詢，而 async 模式不允許這種隱式 I/O
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """每個請求拿到一個獨立的 DB session，請求結束自動關閉。"""
    async with SessionLocal() as session:
        yield session


# scope="request"：session 撐到回應完全送出才關閉，串流結束後還能用它存資料
DbSession = Annotated[AsyncSession, Depends(get_db, scope="request")]
