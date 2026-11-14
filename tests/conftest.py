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
    """Jobs, cache, usage and activity logs go to a temp folder, never into artifacts/."""
    from core.activity import ActivityLog
    from core.pipeline import orchestrator

    monkeypatch.setattr(orchestrator, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(orchestrator, "RUN_ROOT", tmp_path / "runs")
    monkeypatch.setenv("LABFORGE_LOG_DB_URL", "")  # set (even empty), so load_dotenv can't fill it from .env
    monkeypatch.setenv("LABFORGE_DATABASE_URL", "")
    monkeypatch.setenv("LABFORGE_ACTIVITY_LOG", str(tmp_path / "activity.jsonl"))
    if "apps.api.main" in sys.modules:
        monkeypatch.setattr(sys.modules["apps.api.main"], "activity", ActivityLog(path=tmp_path / "activity.jsonl"))
    monkeypatch.setenv("LABFORGE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LABFORGE_ACCOUNTS_DB", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("LABFORGE_REQUIRE_LOGIN", "0")  # tests of sign-in turn it on themselves
    monkeypatch.setenv("LABFORGE_SECRET", "")
    monkeypatch.setenv("LABFORGE_EMAIL_DOMAINS", "cuchd.in")
    monkeypatch.setenv("LABFORGE_FREE_REPORTS", "3")
    monkeypatch.setenv("LABFORGE_FREE_PERIOD", "day")
    monkeypatch.setenv("LABFORGE_MAIL_BACKEND", "")
    monkeypatch.setenv("RESEND_API_KEY", "")
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("LABFORGE_USAGE_LOG", str(tmp_path / "usage.jsonl"))
    monkeypatch.setenv("AI_MODE", "local")
    if "apps.api.main" in sys.modules:
        sys.modules["apps.api.main"].limiter.clear()
    yield
