from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """從環境變數（或 .env 檔）讀取設定，欄位名稱不分大小寫對應環境變數。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    # 模型名稱沒有預設值：沒設定就啟動失敗，避免不小心用錯模型
    llm_model: str
    # 思考模式強度，例如 "none" 可關掉 qwen3 的思考；不設定就不傳給 API
    llm_reasoning_effort: str | None = None
    # 單次 LLM 請求最多等幾秒；串流時是「兩段資料之間」最多等幾秒
    llm_timeout: float = 60.0
    # 連線失敗、逾時、429、5xx 時自動重試幾次（OpenAI SDK 內建指數退避）
    llm_max_retries: int = 2

    # aiosqlite 是 SQLite 的 async 驅動；之後換 PostgreSQL 只要改這串
    database_url: str = "sqlite+aiosqlite:///./app.db"

    # RAG：把文字轉成向量的模型，跟 llm_model 一樣不給預設值
    embedding_model: str
    chroma_path: str = "./chroma_data"

    # 呼叫本服務要帶的 API key，逗號分隔可設多把（每個用戶端一把，方便個別停用或輪替）
    # SecretStr：印出 settings 時會顯示 **********，避免 key 不小心出現在 log
    api_keys: Annotated[list[SecretStr], NoDecode] = Field(min_length=1)
    # 每把 key 每分鐘最多幾個請求
    rate_limit_per_minute: int = 20
    # 允許哪些網域的前端呼叫（逗號分隔）；5173 是 Vite 開發伺服器的預設 port
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    @field_validator("api_keys", "cors_origins", mode="before")
    @classmethod
    def _split_commas(cls, v):
        # NoDecode 讓環境變數以原始字串進來，由這裡自己拆成 list
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


settings = Settings()
