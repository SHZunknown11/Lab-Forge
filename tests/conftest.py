import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["AI_MODE"] = "local"
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Jobs, cache and usage log go to a temp folder, never into artifacts/."""
    from core.pipeline import orchestrator

    monkeypatch.setattr(orchestrator, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setenv("LABFORGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LABFORGE_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("AI_MODE", "local")
    yield
