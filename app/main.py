from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import Base, engine
from app.routers import chat, jobs, sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時建立還不存在的資料表（正式專案會改用 Alembic 做 migration）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 關閉時釋放連線池
    await engine.dispose()


app = FastAPI(title="FastAPI LLM 練習專案", lifespan=lifespan)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(jobs.router)


@app.get("/health")
async def health():
    """健康檢查：給部署平台或監控確認服務還活著。"""
    return {"status": "ok"}
