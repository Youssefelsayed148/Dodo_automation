from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

HAS_DB = all(importlib.util.find_spec(m) is not None for m in ("sqlalchemy", "alembic"))
HAS_API = HAS_DB and importlib.util.find_spec("fastapi") is not None
HAS_WEASY = importlib.util.find_spec("weasyprint") is not None

needs_db = pytest.mark.skipif(not HAS_DB, reason="sqlalchemy/alembic not installed")
needs_api = pytest.mark.skipif(not HAS_API, reason="fastapi not installed")
needs_weasy = pytest.mark.skipif(not HAS_WEASY, reason="weasyprint not installed")


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own data dir, DB and mock providers."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'data' / 'app.db'}")
    monkeypatch.setenv("RUN_WORKER", "0")
    monkeypatch.setenv("IMAGE_PROVIDER", "mock")
    monkeypatch.setenv("TEXT_PROVIDER", "mock")
    monkeypatch.setenv("VISION_PROVIDER", "mock")
    monkeypatch.setenv("MANUAL_MODE", "0")  # existing tests use the mock providers; manual tests switch it on
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "COST_TABLE"):
        monkeypatch.delenv(k, raising=False)
    from app.config import reset_settings_cache
    from app.providers import base, registry
    from app.services import prompts

    reset_settings_cache()
    registry.clear_overrides()
    base.clear_usage_sinks()
    prompts.load_prompt.cache_clear()
    if HAS_DB:
        from app import db

        db.reset_engine()
    yield tmp_path
    if HAS_DB:
        from app import db

        db.reset_engine()
    registry.clear_overrides()
    base.clear_usage_sinks()
    reset_settings_cache()
    os.environ.pop("DATA_DIR", None)


@pytest.fixture
def session():
    if not HAS_DB:
        pytest.skip("sqlalchemy not installed")
    from app.db import SessionLocal, init_db
    from app.services import usage

    init_db()
    usage.install()
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def client():
    if not HAS_API:
        pytest.skip("fastapi not installed")
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def run_jobs() -> int:
    from app.jobs.runner import run_pending_sync

    return run_pending_sync()
