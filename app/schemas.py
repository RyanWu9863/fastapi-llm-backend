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


class JobParseRequest(BaseModel):
    # 限制長度：輸入越長 token 越多，避免有人丟整本書進來燒成本
    description: str = Field(min_length=1, max_length=5000, description="職缺描述全文")


class JobInfo(BaseModel):
    """同時扮演兩個角色：產生給 LLM 的 JSON schema，以及驗證 LLM 的輸出。"""

    title: str = Field(min_length=1, description="職稱，照原文")
    required_skills: list[str] = Field(description="必備技能")
    nice_to_have_skills: list[str] = Field(description="加分技能")
    min_years: int | None = Field(ge=0, le=50, description="最低年資要求（年）；沒提到為 null")


class MessageOut(BaseModel):
    # from_attributes=True：允許直接從 ORM 物件（用屬性存取）轉成 Pydantic model
    model_config = ConfigDict(from_attributes=True)

    role: str
    content: str
    created_at: datetime
