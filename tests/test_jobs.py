import json

import pytest

from app import llm
from app.schemas import JobInfo

VALID = {
    "title": "後端工程師",
    "required_skills": ["Python"],
    "nice_to_have_skills": ["Docker"],
    "min_years": 3,
}


def test_parse_job_success(client, fake_llm):
    fake_llm.replies = [json.dumps(VALID, ensure_ascii=False)]
    r = client.post("/jobs/parse", json={"description": "徵後端工程師"})

    assert r.status_code == 200
    assert r.json() == VALID
    call = fake_llm.calls[0]
    assert call["temperature"] == 0
    assert call["json_schema"] == JobInfo.model_json_schema()
    # 使用者輸入要包在標籤裡，跟指令分開
    assert "<job_description>\n徵後端工程師\n</job_description>" in call["messages"][0]["content"]


def test_parse_job_retries_with_error_feedback(client, fake_llm):
    fake_llm.replies = ["這不是 JSON", json.dumps(VALID)]
    r = client.post("/jobs/parse", json={"description": "徵後端工程師"})

    assert r.status_code == 200
    assert len(fake_llm.calls) == 2
    retry_messages = fake_llm.calls[1]["messages"]
    # 重試時要把錯的輸出和錯誤原因一起給模型
    assert retry_messages[1] == {"role": "assistant", "content": "這不是 JSON"}
    assert "你的輸出有錯誤" in retry_messages[2]["content"]


def test_parse_job_gives_up_after_two_invalid_outputs(client, fake_llm):
    bad = json.dumps({**VALID, "min_years": -1})  # 格式對，但違反 ge=0 的規則
    fake_llm.replies = [bad, bad]
    r = client.post("/jobs/parse", json={"description": "徵後端工程師"})

    assert r.status_code == 502
    assert len(fake_llm.calls) == 2


def test_parse_job_llm_error_returns_502(client, fake_llm):
    fake_llm.replies = [llm.LLMError("掛了")]
    assert client.post("/jobs/parse", json={"description": "徵後端工程師"}).status_code == 502


@pytest.mark.parametrize("description", ["", "字" * 5001], ids=["empty", "too-long"])
def test_parse_job_rejects_bad_input_length(client, fake_llm, description):
    assert client.post("/jobs/parse", json={"description": description}).status_code == 422
    assert fake_llm.calls == []
