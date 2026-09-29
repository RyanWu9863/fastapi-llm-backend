from app import llm
from app.routers import chat as chat_router


def history(client, session_id: str) -> list[tuple[str, str]]:
    return [(m["role"], m["content"]) for m in client.get(f"/sessions/{session_id}/messages").json()]


def test_chat_returns_reply_and_new_session(client, fake_llm):
    fake_llm.replies = ["哈囉"]
    r = client.post("/chat", json={"message": "你好", "system": "你是測試助理"})

    assert r.status_code == 200
    assert r.json()["reply"] == "哈囉"
    assert r.json()["session_id"]
    assert fake_llm.calls[0]["system"] == "你是測試助理"
    assert fake_llm.calls[0]["messages"] == [{"role": "user", "content": "你好"}]


def test_same_session_sends_history_to_llm(client, fake_llm):
    fake_llm.replies = ["你好小明", "你叫小明"]
    sid = client.post("/chat", json={"message": "我叫小明"}).json()["session_id"]
    client.post("/chat", json={"message": "我叫什麼？", "session_id": sid})

    assert fake_llm.calls[1]["messages"] == [
        {"role": "user", "content": "我叫小明"},
        {"role": "assistant", "content": "你好小明"},
        {"role": "user", "content": "我叫什麼？"},
    ]
    assert history(client, sid) == [
        ("user", "我叫小明"), ("assistant", "你好小明"),
        ("user", "我叫什麼？"), ("assistant", "你叫小明"),
    ]


def test_only_recent_history_is_sent(client, fake_llm, monkeypatch):
    monkeypatch.setattr(chat_router, "MAX_HISTORY", 2)
    fake_llm.replies = ["答1", "答2", "答3"]
    sid = client.post("/chat", json={"message": "問1"}).json()["session_id"]
    client.post("/chat", json={"message": "問2", "session_id": sid})
    client.post("/chat", json={"message": "問3", "session_id": sid})

    # 只帶最近 2 則，而且要維持時間順序
    assert fake_llm.calls[2]["messages"] == [
        {"role": "user", "content": "問2"},
        {"role": "assistant", "content": "答2"},
        {"role": "user", "content": "問3"},
    ]


def test_unknown_session_returns_404(client, fake_llm):
    assert client.post("/chat", json={"message": "hi", "session_id": "nope"}).status_code == 404
    assert client.get("/sessions/nope/messages").status_code == 404
    assert fake_llm.calls == []


def test_empty_message_returns_422(client, fake_llm):
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert fake_llm.calls == []


def test_llm_error_returns_502_and_saves_nothing(client, fake_llm):
    fake_llm.replies = ["第一輪回答", llm.LLMError("掛了")]
    sid = client.post("/chat", json={"message": "第一輪"}).json()["session_id"]
    r = client.post("/chat", json={"message": "第二輪", "session_id": sid})

    assert r.status_code == 502
    assert history(client, sid) == [("user", "第一輪"), ("assistant", "第一輪回答")]


def test_stream_returns_text_and_saves_turn(client, fake_llm):
    fake_llm.stream_parts = ["你", "好", "！"]
    with client.stream("POST", "/chat/stream", json={"message": "嗨"}) as r:
        assert r.status_code == 200
        sid = r.headers["X-Session-Id"]
        text = "".join(r.iter_text())

    assert text == "你好！"
    assert history(client, sid) == [("user", "嗨"), ("assistant", "你好！")]


def test_stream_connect_error_returns_502(client, fake_llm):
    fake_llm.stream_error = llm.LLMError("連不上")
    assert client.post("/chat/stream", json={"message": "嗨"}).status_code == 502


def test_stream_mid_failure_marks_error_and_saves_nothing(client, fake_llm):
    fake_llm.replies = ["第一輪回答"]
    sid = client.post("/chat", json={"message": "第一輪"}).json()["session_id"]
    fake_llm.stream_parts = ["一半", llm.LLMError("斷了")]
    r = client.post("/chat/stream", json={"message": "第二輪", "session_id": sid})

    # 狀態碼已經送出 200，只能在內容最後標示錯誤
    assert r.status_code == 200
    assert r.text.startswith("一半")
    assert "[錯誤：LLM 回應中斷]" in r.text
    assert history(client, sid) == [("user", "第一輪"), ("assistant", "第一輪回答")]
