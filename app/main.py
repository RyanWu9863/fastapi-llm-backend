import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, engine
from app.logs import setup_logging
from app.routers import chat, jobs, rag, sessions
from app.security import rate_limit

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 啟動時建立還不存在的資料表（正式專案會改用 Alembic 做 migration）
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 關閉時釋放連線池
    await engine.dispose()


app = FastAPI(title="FastAPI LLM 練習專案", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    status = 500  # call_next 丟出例外時，實際回給用戶端的就是 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # 只記 path 不記 query string 和 header：那裡可能有 key 或個資
        # 串流回應的耗時只算到「開始回傳」為止，完整生成時間看 llm_stream 那筆 log
        logger.info(
            "request",
            extra={"fields": {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000),
                "client_id": getattr(request.state, "client_id", None),
            }},
        )


# CORS 要最後加：後加的 middleware 包在最外層，連 401、429 的回應也會帶 CORS header，
# 前端才看得到真正的錯誤，而不是瀏覽器擋下來的 CORS 錯誤
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
    # 瀏覽器預設讀不到自訂 header，要明確開放前端才拿得到串流的 session_id
    expose_headers=["X-Session-Id"],
)

# 除了 /health 以外都要驗證 API key 並限流（rate_limit 內部會先驗證 key）
protected = [Depends(rate_limit)]
app.include_router(chat.router, dependencies=protected)
app.include_router(sessions.router, dependencies=protected)
app.include_router(jobs.router, dependencies=protected)
app.include_router(rag.router, dependencies=protected)


@app.get("/health")
async def health():
    """健康檢查：給部署平台或監控確認服務還活著，不需要 API key。"""
    return {"status": "ok"}
