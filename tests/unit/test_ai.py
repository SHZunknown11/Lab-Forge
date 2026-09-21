import json
import sys
from types import SimpleNamespace

import pytest
from pathlib import Path
from core.schemas import ExperimentDocument, ExperimentMetadata, ExperimentLevel
from core.ai.provider import AIOrchestrator, GeminiProvider, LocalMockProvider

def test_ai_orchestrator_caching(tmp_path):
    orchestrator = AIOrchestrator(cache_dir=tmp_path)
    # mock document
    doc = ExperimentDocument(
        metadata=ExperimentMetadata(experiment_number="1", title="T", aim="A"),
        easy=ExperimentLevel(problem_statement="Easy P")
    )
    
    # generate once
    generated1 = orchestrator.generate(doc)
    assert generated1.experiment_number == "1"
    
    # check cache file exists
    cache_file = tmp_path / "exp_1_LocalMockProvider_mock-local_cache.json"
    assert cache_file.exists()
    
    # generate again, should use cache (even if we changed the provider mock)
    orchestrator.provider = LocalMockProvider() # new instance, doesn't matter, it reads from cache
    generated2 = orchestrator.generate(doc)
    assert generated1.model_dump() == generated2.model_dump()


def test_gemini_provider_uses_configured_model_and_json_schema(monkeypatch):
    calls = []

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(text=json.dumps({
                "experiment_number": "1",
                "title": "Generated",
                "global_aim": "Aim",
                "easy": {
                    "problem_statement": "Easy", "objectives": "Learn",
                    "filename": "Easy.java", "code": "public class Easy {}",
                    "expected_behavior": "Works",
                },
                "medium": {
                    "problem_statement": "Medium", "objectives": "Learn",
                    "filename": "Medium.java", "code": "public class Medium {}",
                    "expected_behavior": "Works",
                },
                "hard": {
                    "problem_statement": "Hard", "objectives": "Learn",
                    "filename": "Hard.java", "code": "public class Hard {}",
                    "expected_behavior": "Works",
                },
                "learning_outcomes": ["Learn"],
            }))

    class FakeClient:
        def __init__(self, api_key):
            assert api_key == "test-key"
            self.models = FakeModels()

    fake_genai = SimpleNamespace(Client=FakeClient)
    fake_types = SimpleNamespace(GenerateContentConfig=FakeConfig)
    fake_errors = SimpleNamespace(APIError=Exception)
    fake_genai.types = fake_types
    fake_genai.errors = fake_errors
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")

    provider = GeminiProvider()
    document = ExperimentDocument(
        metadata=ExperimentMetadata(experiment_number="1", title="T", aim="A"),
        easy=ExperimentLevel(problem_statement="Easy"),
    )
    result = provider.generate_experiment(document)

    assert result.title == "Generated"
    assert provider.get_metadata()["model"] == "gemini-test-model"
    assert calls[0]["model"] == "gemini-test-model"
    assert calls[0]["config"].kwargs["response_mime_type"] == "application/json"


def test_gemini_provider_retries_with_a_fallback_model(monkeypatch):
    calls = []

    class RetryableError(Exception):
        code = 503

    class FakeConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RetryableError("temporarily unavailable")
            return SimpleNamespace(text="{}")

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    fake_genai = SimpleNamespace(Client=FakeClient)
    fake_types = SimpleNamespace(GenerateContentConfig=FakeConfig)
    fake_errors = SimpleNamespace(APIError=RetryableError)
    fake_genai.types = fake_types
    fake_genai.errors = fake_errors
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    monkeypatch.setitem(sys.modules, "google.genai.errors", fake_errors)
    monkeypatch.setattr("core.ai.provider.time.sleep", lambda _: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "primary")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "fallback")
    monkeypatch.setenv("GEMINI_MAX_ATTEMPTS", "2")

    provider = GeminiProvider()

    assert provider._generate_json("prompt", dict) == {}
    assert [call["model"] for call in calls] == ["primary", "fallback"]
