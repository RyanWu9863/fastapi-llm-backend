import hashlib
import math
import secrets
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from app.config import settings

# 用 APIKeyHeader 宣告：/docs 會出現 Authorize 按鈕，可以在 Swagger 裡填 key
# auto_error=False：缺 key 時由我們自己回 401 和中文訊息
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    request: Request, api_key: Annotated[str | None, Security(_api_key_header)]
) -> str:
    """驗證 X-API-Key，回傳這把 key 的代號（client_id）。"""
    # compare_digest：比對時間固定，避免攻擊者從回應快慢一個字一個字猜出 key（timing attack）
    if not api_key or not any(
        secrets.compare_digest(api_key.encode(), k.get_secret_value().encode())
        for k in settings.api_keys
    ):
        raise HTTPException(status_code=401, detail="缺少或無效的 API key，請在 header 帶 X-API-Key")
    # 用 hash 前 8 碼當代號：log 和限流都認得出是哪個用戶端，但不會洩漏 key 本身
    client_id = hashlib.sha256(api_key.encode()).hexdigest()[:8]
    request.state.client_id = client_id  # 給 log middleware 用
    return client_id


class RateLimiter:
    """滑動視窗限流：記錄每個用戶端最近 window 秒內的請求時間，超過 limit 就拒絕。

    資料存在記憶體：只適用單一 process。開多個 worker 或多台機器時，
    每個 process 各算各的，要改用 Redis 這類共用儲存。
    """

    def __init__(self, limit: int, window: float = 60.0, clock=time.monotonic):
        self.limit = limit
        self.window = window
        # 時鐘可以從外面傳入：測試時換成假時鐘，就能模擬「過了 60 秒」而不用真的等
        # 預設用 monotonic 而不是 time.time()：不受系統校時影響
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, client_id: str) -> float | None:
        """允許就記一筆並回傳 None；拒絕就回傳還要等幾秒。"""
        now = self._clock()
        hits = self._hits[client_id]
        while hits and hits[0] <= now - self.window:
            hits.popleft()  # 丟掉視窗外的舊紀錄
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        return None


_limiter = RateLimiter(settings.rate_limit_per_minute)


async def rate_limit(client_id: Annotated[str, Depends(require_api_key)]) -> None:
    """依賴 require_api_key：先驗證身分，再依用戶端限流。"""
    retry_after = _limiter.check(client_id)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="請求太頻繁，請稍後再試",
            # Retry-After：告訴用戶端幾秒後可以再試，寫得好的用戶端會照著等
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
