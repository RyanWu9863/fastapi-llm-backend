from fastapi import FastAPI

app = FastAPI(title="FastAPI LLM 練習專案")


@app.get("/health")
async def health():
    """健康檢查：給部署平台或監控確認服務還活著。"""
    return {"status": "ok"}
