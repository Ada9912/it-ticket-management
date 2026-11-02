import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.api.ai_assistant import TriageRequest, triage_issue


@pytest.mark.parametrize("failure,expected", [
    ("timeout", "超时"), ("network", "无法连接"),
    (401, "认证失败"), (402, "余额不足"), (429, "频率受限"), (503, "暂不可用"),
    ("empty", "不符合要求"), ("invalid", "不符合要求"),
])
def test_model_failures_use_explicit_rule_fallback(monkeypatch, failure, expected):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-not-real")
    response = MagicMock()
    with patch("app.api.ai_assistant.httpx.Client") as factory:
        post = factory.return_value.__enter__.return_value.post
        post.return_value = response
        if failure == "timeout":
            post.side_effect = httpx.ReadTimeout("test")
        elif failure == "network":
            post.side_effect = httpx.ConnectError("test")
        elif isinstance(failure, int):
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "test", request=httpx.Request("POST", "https://api.deepseek.com"),
                response=httpx.Response(failure))
        else:
            content = "" if failure == "empty" else json.dumps({"category": "Wrong"})
            response.json.return_value = {"choices": [{"message": {"content": content}}]}
        result = triage_issue(TriageRequest(issue_text="电脑屏幕不亮"))
    assert result["category"] == "Hardware"
    assert expected in result["method"]
    assert result["human_review_required"] is True
    assert "test-only-not-real" not in json.dumps(result)


def test_feedback_rejects_invalid_then_accepts_corrected_submission(client):
    body = {"issue_text": "电脑屏幕不亮", "suggested_category": "Hardware",
            "final_category": "Hardware", "selected_action": "EDITED"}
    assert client.post("/ai/feedback", json=body).status_code == 422
    body["final_category"] = "Other"
    assert client.post("/ai/feedback", json=body).status_code == 200
    rows = client.get("/ai/feedback").json()
    assert rows[0]["suggested_category"] == "Hardware"
    assert rows[0]["final_category"] == "Other"
