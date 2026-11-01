import json

import httpx
import pytest

from core.ai.provider import (
    AIError, DraftCache, OpenAICompatProvider, ProviderChain, RetryableAIError, build_user_prompt,
)
from core.schemas import AIReport

REPORT = {
    "experiment_no": "2.1", "title": "Experiment 2.1", "aim": "Sort numbers.",
    "tasks": [{"title": "Task", "problem": "Sort.", "objectives": ["Learn sorting"], "language": "python",
               "files": [{"name": "main.py", "code": "print(sorted([3, 1, 2]))"}], "stdin": ""}],
    "learning_outcomes": ["Sorting works."],
}


def test_cache_key_ignores_whitespace_and_case_but_not_language(tmp_path):
    k1 = DraftCache.key("Aim: Sort\n\n numbers", "python")
    assert k1 == DraftCache.key("aim: sort numbers", "python")
    assert k1 != DraftCache.key("aim: sort numbers", "java")
    cache = DraftCache(tmp_path)
    assert cache.get(k1) is None
    cache.put(k1, AIReport.model_validate(REPORT))
    assert cache.get(k1).aim == "Sort numbers."


def test_prompt_contains_only_what_is_needed():
    prompt = build_user_prompt("Aim: x", language="auto", subject="CC")
    assert "Subject: CC" in prompt and "Write the programs in" not in prompt


def _provider(handler, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    return OpenAICompatProvider("groq", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_openai_compatible_provider_parses_json_and_logs_usage(monkeypatch, tmp_path):
    seen = {}

    def handler(request: httpx.Request):
        body = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        seen["format"] = body.get("response_format")
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(REPORT)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 400},
        })

    report = _provider(handler, monkeypatch).generate("Aim: sort numbers")
    assert report.tasks[0].files[0].name == "main.py"
    assert seen["auth"] == "Bearer test-key" and seen["format"] == {"type": "json_object"}
    log = (tmp_path / "usage.jsonl").read_text().strip().splitlines()
    assert json.loads(log[-1])["input"] == 900


def test_rate_limited_provider_is_retryable(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    provider = _provider(lambda r: httpx.Response(429, text="slow down"), monkeypatch)
    with pytest.raises(RetryableAIError):
        provider.generate("Aim: x")


class Fake:
    def __init__(self, name, result=None, error=None):
        self.name, self.model, self.configured = name, "m", True
        self.result, self.error, self.calls = result, error, 0

    def generate(self, *a, **k):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def test_chain_falls_through_to_the_next_provider():
    broken = Fake("a", error=RetryableAIError("quota"))
    working = Fake("b", result=AIReport.model_validate(REPORT))
    chain = ProviderChain([broken, working])
    assert chain.generate("sheet").aim == "Sort numbers."
    assert broken.calls == working.calls == 1


def test_chain_reports_a_plain_message_when_everything_fails():
    chain = ProviderChain([Fake("a", error=RetryableAIError("x")), Fake("b", error=RetryableAIError("y"))])
    with pytest.raises(AIError, match="busy or out of free quota"):
        chain.generate("sheet")


def test_unconfigured_chain_explains_itself():
    with pytest.raises(AIError, match="No AI provider"):
        ProviderChain([]).generate("sheet")


def test_cloudflare_provider_needs_both_key_and_url(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_AI_KEY", "k")
    monkeypatch.delenv("CLOUDFLARE_BASE_URL", raising=False)
    assert not OpenAICompatProvider("cloudflare").configured
    monkeypatch.setenv("CLOUDFLARE_BASE_URL", "https://labforge-ai.example.workers.dev/v1/")
    p = OpenAICompatProvider("cloudflare")
    assert p.configured and p.base == "https://labforge-ai.example.workers.dev/v1"


def test_gpt_oss_gets_low_reasoning_effort(monkeypatch):
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(REPORT)}}], "usage": {}})

    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setattr("core.ai.provider.log_usage", lambda *a, **k: {})
    OpenAICompatProvider("groq", client=httpx.Client(transport=httpx.MockTransport(handler))).generate("Aim: x")
    assert sent["reasoning_effort"] == "low" and sent["model"] == "openai/gpt-oss-120b"
