# FastAPI + LLM 學習專案說明

> 給 AI 程式助理的專案說明。請依照本文件，一步一步陪我完成這個專案。

## 我的背景與目標

- 目標職缺：後端 Python 工程師 / LLM 應用開發
- 目的：一邊學 FastAPI，一邊做出可以放進履歷、面試時講得清楚的 LLM 後端服務
- 程度：會 Python 基礎，FastAPI 和 LLM API 還在學

## 請你協助的方式

1. **一次只做一個階段**。完成、測試通過後，等我確認才進入下一階段。
2. 每次新增程式碼時，**簡短說明它為什麼這樣寫**（例如為什麼用 async、為什麼用 Pydantic），我是在學習，不只是要成品。
3. 每個階段結束時，列出**這階段面試可能會被問的 2～3 個問題**。
4. API key 一律從環境變數讀取，**不要寫死在程式碼裡**，也不要 commit `.env`。
5. 模型名稱用環境變數 `LLM_MODEL` 設定，不要寫死。
6. 程式碼註解和說明用繁體中文。

## 技術選型

| 項目 | 選擇 |
|---|---|
| Web 框架 | FastAPI（`fastapi[standard]`） |
| 資料驗證 | Pydantic v2 |
| LLM SDK | `anthropic`（AsyncAnthropic）。可替換為 OpenAI SDK，或用 Ollama 的 OpenAI 相容 API 在本機免費練習 |
| 資料庫 | SQLAlchemy 2.x + SQLite（之後可換 PostgreSQL） |
| 向量資料庫 | Chroma 或 pgvector（階段 4） |
| 測試 | pytest + FastAPI `TestClient`，LLM 呼叫要 mock |
| 部署 | Docker |

## 預期目錄結構

```
fastapi-llm/
├── app/
│   ├── main.py            # 建立 FastAPI app、掛載 router
│   ├── config.py          # 用 pydantic-settings 讀環境變數
│   ├── schemas.py         # Pydantic request/response models
│   ├── llm.py             # 包裝 LLM client（方便測試時 mock）
│   ├── db.py              # 資料庫連線與 session
│   ├── models.py          # SQLAlchemy ORM models
│   └── routers/
│       └── chat.py        # /chat 相關路由
├── tests/
│   └── test_chat.py
├── .env.example
├── .gitignore
├── requirements.txt
├── Dockerfile
└── README.md
```

## 開發階段

### 階段 0：環境建置

- 建立虛擬環境、`requirements.txt`、`.env.example`、`.gitignore`
- 一個 `GET /health` 回傳 `{"status": "ok"}`
- **驗收**：`fastapi dev app/main.py` 能啟動，`http://127.0.0.1:8000/docs` 看得到 API 文件

### 階段 1：基本對話 API

- `POST /chat`：輸入 `message`、可選的 `system`，回傳 `reply`
- `POST /chat/stream`：用 `StreamingResponse` 串流回傳
- LLM 呼叫失敗時回 `502`，錯誤訊息清楚
- **學習重點**：Pydantic model、`response_model`、async/await、`HTTPException`
- **驗收**：在 `/docs` 裡兩個 API 都能正常呼叫

參考寫法：

```python
import os
import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

app = FastAPI()
client = anthropic.AsyncAnthropic()   # 自動讀取 ANTHROPIC_API_KEY
MODEL = os.environ["LLM_MODEL"]

class ChatRequest(BaseModel):
    message: str
    system: str = "你是一個有幫助的助理，用繁體中文回答。"

class ChatResponse(BaseModel):
    reply: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=req.system,
            messages=[{"role": "user", "content": req.message}],
        )
    except anthropic.APIError as e:
        raise HTTPException(status_code=502, detail=f"LLM 呼叫失敗：{e}")
    return ChatResponse(reply=resp.content[0].text)

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        async with client.messages.stream(
            model=MODEL,
            max_tokens=1024,
            system=req.system,
            messages=[{"role": "user", "content": req.message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    return StreamingResponse(generate(), media_type="text/plain")
```

### 階段 2：多輪對話與資料庫

- 新增 `session_id`，把每輪 user / assistant 訊息存進資料庫
- 呼叫 LLM 時帶入該 session 的歷史訊息
- `GET /sessions/{session_id}/messages` 查詢對話紀錄
- **學習重點**：SQLAlchemy ORM、`Depends` 注入 DB session
- **驗收**：同一個 `session_id` 連續問兩個有關聯的問題，第二題能正確引用上文

### 階段 3：結構化輸出

- 新增一個 API（例如：輸入一段職缺描述，回傳 `{職稱, 必備技能[], 加分技能[], 年資}`）
- 要求 LLM 回傳 JSON，用 Pydantic 驗證；驗證失敗時重試一次或回傳明確錯誤
- **學習重點**：prompt 設計、資料驗證、LLM 輸出不可信的處理
- **驗收**：輸入幾份不同的職缺描述都能拿到格式正確的 JSON

### 階段 4：RAG（文件問答）

- `POST /documents`：上傳文字檔 → 切塊 → 產生 embedding → 存進向量資料庫
- `POST /ask`：檢索相關片段 → 放進 prompt → 回答並附上引用的來源片段
- **學習重點**：chunking 策略、embedding、檢索與 prompt 組合
- **驗收**：問文件內才有的問題能答對，問文件外的問題會說不知道

### 階段 5：正式環境的基本功

- 用 `Depends` 實作簡單的 API key 驗證（header：`X-API-Key`）
- 簡易 rate limit
- LLM 呼叫加上 timeout 和 retry
- 結構化 logging（記錄耗時、token 用量，不記錄 API key）
- CORS 設定
- **驗收**：沒帶 key 回 `401`，超過頻率回 `429`

### 階段 6：測試與部署

- pytest：用 `TestClient` 測試所有 API，**把 LLM client mock 掉**（測試不應該真的打 API）
- 撰寫 `Dockerfile`，能用 `docker run` 啟動
- 完成 `README.md`：專案介紹、架構圖、啟動方式、API 說明、技術選擇的理由
- **驗收**：`pytest` 全部通過；`docker build` 和 `docker run` 成功

## 完成後我應該能在面試回答

- 為什麼 FastAPI 適合 LLM 服務？async 帶來什麼好處？
- 串流回應是怎麼實作的？前端要怎麼接？
- LLM API 逾時、失敗或回傳格式錯誤時，你怎麼處理？
- 測試時怎麼避免真的呼叫 LLM？
- RAG 的流程是什麼？chunk 大小怎麼決定？
- 如何控制 API 成本與濫用？

## 參考資源

- FastAPI 官方教學（有繁中翻譯）：https://fastapi.tiangolo.com/tutorial/
- Anthropic API 文件：https://docs.claude.com
- Pydantic 文件：https://docs.pydantic.dev
- SQLAlchemy 2.0 教學：https://docs.sqlalchemy.org/en/20/tutorial/
