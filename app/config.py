from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """從環境變數（或 .env 檔）讀取設定，欄位名稱不分大小寫對應環境變數。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    # 模型名稱沒有預設值：沒設定就啟動失敗，避免不小心用錯模型
    llm_model: str
    # 思考模式強度，例如 "none" 可關掉 qwen3 的思考；不設定就不傳給 API
    llm_reasoning_effort: str | None = None

    # aiosqlite 是 SQLite 的 async 驅動；之後換 PostgreSQL 只要改這串
    database_url: str = "sqlite+aiosqlite:///./app.db"


settings = Settings()
