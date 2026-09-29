from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """從環境變數（或 .env 檔）讀取設定，欄位名稱不分大小寫對應環境變數。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    # 模型名稱沒有預設值：沒設定就啟動失敗，避免不小心用錯模型
    llm_model: str


settings = Settings()
