from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_SYSTEM = "你是一個有幫助的助理，用繁體中文回答。"


class ChatRequest(BaseModel):
    # min_length=1：空字串在進到 LLM 之前就被擋下，回 422
    message: str = Field(min_length=1, description="使用者的訊息")
    system: str = Field(default=DEFAULT_SYSTEM, description="系統提示詞，設定助理的角色與規則")
    session_id: str | None = Field(default=None, description="延續既有對話；不帶則開新對話")


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class MessageOut(BaseModel):
    # from_attributes=True：允許直接從 ORM 物件（用屬性存取）轉成 Pydantic model
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime
