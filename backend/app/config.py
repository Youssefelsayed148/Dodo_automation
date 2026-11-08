"""Application configuration, read from environment variables (and `.env`).

Kept dependency-free on purpose (plain pydantic + os.environ) so that pure
service modules can be imported and tested without the web stack.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing env vars win."""
    for candidate in (REPO_ROOT / ".env", BACKEND_DIR / ".env"):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


class Settings(BaseModel):
    data_dir: Path
    database_url: str
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    public_base_url: str = "http://127.0.0.1:8000"

    # Providers (names are configuration, not code)
    text_provider: str = "mock"
    vision_provider: str = "mock"
    image_provider: str = "mock"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_base_url: str = "https://api.anthropic.com"

    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1"
    openai_base_url: str = "https://api.openai.com"

    gemini_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"

    google_client_id: str = ""
    google_client_secret: str = ""

    # Optional cost table overrides: "provider:model=usd_per_unit,..."
    cost_table: str = ""

    run_worker: bool = True
    http_timeout: float = 120.0

    @property
    def books_dir(self) -> Path:
        return self.data_dir / "books"

    @property
    def compare_dir(self) -> Path:
        return self.data_dir / "compare"

    @property
    def library_dir(self) -> Path:
        return self.data_dir / "library"

    @property
    def tmp_dir(self) -> Path:
        return self.data_dir / "tmp"

    @property
    def google_token_path(self) -> Path:
        return self.data_dir / "google_token.json"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    data_dir = Path(_env("DATA_DIR", str(REPO_ROOT / "data"))).resolve()
    db_url = _env("DATABASE_URL", "sqlite:///data/app.db")
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
        rel = db_url[len("sqlite:///"):]
        if rel != ":memory:":
            p = Path(rel)
            if not p.is_absolute():
                # "data/..." lives in DATA_DIR; other relative paths are repo-relative
                p = data_dir / p.relative_to("data") if p.parts and p.parts[0] == "data" else REPO_ROOT / p
            db_url = f"sqlite:///{p}"
    cors = [o.strip() for o in _env("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",") if o.strip()]
    s = Settings(
        data_dir=data_dir,
        database_url=db_url,
        host=_env("HOST", "127.0.0.1"),
        port=int(_env("PORT", "8000")),
        cors_origins=cors,
        public_base_url=_env("PUBLIC_BASE_URL", f"http://127.0.0.1:{_env('PORT', '8000')}"),
        text_provider=_env("TEXT_PROVIDER", "") or ("anthropic" if _env("ANTHROPIC_API_KEY") else "mock"),
        vision_provider=_env("VISION_PROVIDER", "") or ("anthropic" if _env("ANTHROPIC_API_KEY") else "mock"),
        image_provider=_env("IMAGE_PROVIDER", "mock"),
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-opus-5-5"),
        anthropic_base_url=_env("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
        openai_api_key=_env("OPENAI_API_KEY"),
        openai_image_model=_env("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com"),
        gemini_api_key=_env("GEMINI_API_KEY"),
        gemini_image_model=_env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        gemini_base_url=_env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com"),
        google_client_id=_env("GOOGLE_CLIENT_ID"),
        google_client_secret=_env("GOOGLE_CLIENT_SECRET"),
        cost_table=_env("COST_TABLE"),
        run_worker=_env("RUN_WORKER", "1") not in ("0", "false", "no"),
        http_timeout=float(_env("HTTP_TIMEOUT", "120")),
    )
    for d in (s.data_dir, s.books_dir, s.compare_dir, s.library_dir, s.tmp_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


def reset_settings_cache() -> None:
    get_settings.cache_clear()
