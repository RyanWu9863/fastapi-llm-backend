import pytest

from app import rag
from app.rag import split_text

HANDBOOK = "## 遠端工作\n每週可以遠端工作兩天。\n\n## 餐費補助\n每月餐費補助兩千四百元。"


@pytest.fixture(autouse=True)
def empty_vector_store():
    """每個測試開始前清空向量資料庫，讓測試之間互不影響。"""
    ids = rag._collection.get()["ids"]
    if ids:
        rag._collection.delete(ids=ids)


def upload(client, data: str | bytes, filename: str = "doc.md"):
    if isinstance(data, str):
        data = data.encode()
    return client.post("/documents", files={"file": (filename, data)})


# ── 切塊 ──


def test_split_keeps_heading_with_its_content():
    text = "# 手冊\n\n## 第一章\n內容一\n\n## 第二章\n內容二"
    # 只有標題的「# 手冊」會併進下一章；每個標題都跟自己的內容在同一塊
    assert split_text(text) == ["# 手冊\n## 第一章\n內容一", "## 第二章\n內容二"]


def test_long_section_is_split_and_later_chunks_get_heading():
    text = "## 長章節\n\n" + "\n\n".join(["甲" * 150, "乙" * 150, "丙" * 150])
    chunks = split_text(text, chunk_size=400)

    assert len(chunks) == 2
    assert chunks[0].startswith("## 長章節\n甲")
    assert chunks[1] == "## 長章節\n" + "丙" * 150


def test_long_paragraph_is_hard_split_with_overlap():
    text = "".join(str(i % 10) for i in range(1000))
    chunks = split_text(text, chunk_size=400, overlap=80)

    assert all(len(c) <= 400 for c in chunks)
    assert chunks[1][:80] == chunks[0][-80:]  # 相鄰兩塊重疊 80 字
    # 扣掉重疊部分接回去，要跟原文一模一樣（沒有漏字）
    assert chunks[0] + "".join(c[80:] for c in chunks[1:]) == text


def test_split_blank_text_returns_nothing():
    assert split_text("  \n\n  ") == []


# ── 上傳 ──


def test_upload_document(client):
    r = upload(client, HANDBOOK)

    assert r.status_code == 201
    assert r.json()["filename"] == "doc.md"
    assert r.json()["chunks"] == 2


@pytest.mark.parametrize(
    "data, status",
    [
        ("中文".encode("big5"), 400),  # 不是 UTF-8
        (b"  \n\n  ", 400),  # 沒有內容
        (b"a" * 1_000_001, 413),  # 超過 1 MB
    ],
    # 自訂測試名稱：否則 pytest 會把 1 MB 的內容塞進名稱，超過 Windows 環境變數長度上限
    ids=["not-utf8", "blank", "over-1mb"],
)
def test_upload_rejects_bad_files(client, data, status):
    assert upload(client, data).status_code == status


# ── 問答 ──


def test_ask_without_documents_skips_llm(client, fake_llm):
    r = client.post("/ask", json={"question": "每週可以遠端幾天？"})

    assert "還沒有上傳" in r.json()["answer"]
    assert r.json()["sources"] == []
    assert fake_llm.calls == []


def test_ask_puts_retrieved_chunk_into_prompt(client, fake_llm):
    upload(client, HANDBOOK)
    fake_llm.replies = ["每週可以遠端兩天 [1]"]
    r = client.post("/ask", json={"question": "每週可以遠端工作幾天？", "top_k": 1})

    assert r.json()["answer"] == "每週可以遠端兩天 [1]"
    prompt = fake_llm.calls[0]["messages"][0]["content"]
    assert "[1]" in prompt
    assert "每週可以遠端工作兩天" in prompt
    assert "餐費" not in prompt  # top_k=1，只放最相關的那一塊


def test_ask_returns_only_cited_sources(client, fake_llm):
    upload(client, HANDBOOK)
    fake_llm.replies = ["餐費補助是每月兩千四百元 [2]"]
    r = client.post("/ask", json={"question": "每週可以遠端工作幾天？", "top_k": 2})

    sources = r.json()["sources"]
    assert len(sources) == 1  # 檢索到 2 塊，但回答只引用了 [2]
    assert "餐費" in sources[0]["text"]


def test_ask_unknown_answer_has_no_sources(client, fake_llm):
    upload(client, HANDBOOK)
    fake_llm.replies = ["文件中沒有相關資訊，我不知道。"]
    r = client.post("/ask", json={"question": "年終獎金有幾個月？"})

    assert r.json()["sources"] == []
