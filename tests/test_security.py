import pytest

from app import security
from app.security import RateLimiter

PROTECTED = [
    ("POST", "/chat"),
    ("POST", "/chat/stream"),
    ("GET", "/sessions/x/messages"),
    ("POST", "/jobs/parse"),
    ("POST", "/documents"),
    ("POST", "/ask"),
]


def test_health_needs_no_key(anon_client):
    assert anon_client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong-key"}], ids=["no-key", "wrong-key"])
@pytest.mark.parametrize("method, path", PROTECTED)
def test_protected_routes_require_valid_key(anon_client, headers, method, path):
    # 驗證在最前面：就算 body 不合法，也是先回 401 而不是 422
    assert anon_client.request(method, path, headers=headers, json={}).status_code == 401


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(security, "_limiter", RateLimiter(limit=2))
    codes = [client.get("/sessions/x/messages").status_code for _ in range(3)]

    assert codes == [404, 404, 429]  # 前兩次通過驗證和限流（session 不存在所以 404）
    assert int(client.get("/sessions/x/messages").headers["Retry-After"]) > 0


def test_rate_limiter_sliding_window():
    now = 0.0
    limiter = RateLimiter(limit=2, window=60, clock=lambda: now)

    assert limiter.check("a") is None
    now = 30
    assert limiter.check("a") is None
    now = 40
    assert limiter.check("a") == pytest.approx(20)  # 第 1 筆在 60 秒時過期，還要等 20 秒
    assert limiter.check("b") is None  # 每個用戶端分開計算
    now = 61
    assert limiter.check("a") is None  # 第 1 筆過期，空出名額


def test_cors_headers_present_even_on_401(anon_client):
    origin = {"Origin": "http://localhost:5173"}
    preflight = anon_client.options(
        "/chat",
        headers={**origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-api-key"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"

    r = anon_client.get("/sessions/x/messages", headers=origin)
    assert r.status_code == 401
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert r.headers["access-control-expose-headers"] == "X-Session-Id"
