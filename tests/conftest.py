"""測試共用的設定與 fixture。

app 的設定在 import 時就會讀取，所以一定要在 import app 之前先設定好環境變數。
"""

import atexit
import os
import shutil
import tempfile
import zlib
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="fastapi-llm-test-"))
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
os.environ.update({
    # 用暫存目錄裡全新的資料庫，不會動到開發用的 app.db 和 chroma_data
    "DATABASE_URL": f"sqlite+aiosqlite:///{(_tmp / 'test.db').as_posix()}",
    "CHROMA_PATH": (_tmp / "chroma").as_posix(),
    "API_KEYS": "test-key",
    "LLM_MODEL": "fake-model",
    "EMBEDDING_MODEL": "fake-embedding",
    # 萬一有測試忘了 mock，會連到不存在的位址而立刻失敗，不會真的打到 LLM
    "LLM_BASE_URL": "http://127.0.0.1:9/v1",
    "LLM_MAX_RETRIES": "0",
    # 限流另外有專門的測試；其他測試不要被限流干擾
    "RATE_LIMIT_PER_MINUTE": "1000",
    "CORS_ORIGINS": "http://localhost:5173",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = "test-key"


def fake_vector(text: str) -> list[float]:
    """假 embedding：把每個字雜湊到 256 維裡計數。

    共用的字越多，向量就越接近，足以測試「檢索有沒有挑到對的片段」。
    """
    v = [0.0] * 256
    for ch in text:
        v[zlib.crc32(ch.encode()) % 256] += 1.0
    return v


class FakeLLM:
    """取代 app.llm 的假 LLM：回傳預先排好的內容，並記錄每次被呼叫時收到的參數。"""

    def __init__(self):
        self.replies: list = []  # chat() 依序回傳；放 Exception 代表這次呼叫失敗
        self.stream_parts: list = ["你", "好"]  # stream_chat() 依序吐出；放 Exception 代表串流途中失敗
        self.stream_error: Exception | None = None  # 設定後 stream_chat() 在建立連線時就失敗
        self.calls: list[dict] = []

    async def chat(self, messages, system, **kwargs):
        # 複製一份：router 之後可能會修改同一個 list，測試要看的是「當下」送出的內容
        self.calls.append({"messages": list(messages), "system": system, **kwargs})
        reply = self.replies.pop(0) if self.replies else "假回答"
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def stream_chat(self, messages, system):
        self.calls.append({"messages": list(messages), "system": system})
        if self.stream_error:
            raise self.stream_error
        parts = list(self.stream_parts)

        async def gen():
            for part in parts:
                if isinstance(part, Exception):
                    raise part
                yield part

        return gen()

    async def embed(self, texts):
        return [fake_vector(t) for t in texts]


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch) -> FakeLLM:
    """autouse：每個測試都自動套用，保證測試永遠不會真的呼叫 LLM。"""
    fake = FakeLLM()
    monkeypatch.setattr(llm, "chat", fake.chat)
    monkeypatch.setattr(llm, "stream_chat", fake.stream_chat)
    monkeypatch.setattr(llm, "embed", fake.embed)
    return fake


@pytest.fixture
def client():
    """帶正確 API key 的用戶端。

    用 with：會觸發 lifespan（建立資料表），而且整個測試共用同一個 event loop。
    """
    with TestClient(app, headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def anon_client():
    """不帶 API key 的用戶端。"""
    with TestClient(app) as c:
        yield c
