from pydantic import BaseModel, Field

DEFAULT_SYSTEM = "你是一個有幫助的助理，用繁體中文回答。"


class ChatRequest(BaseModel):
    # min_length=1：空字串在進到 LLM 之前就被擋下，回 422
    message: str = Field(min_length=1, description="使用者的訊息")
    system: str = Field(default=DEFAULT_SYSTEM, description="系統提示詞，設定助理的角色與規則")


class ChatResponse(BaseModel):
    reply: str
