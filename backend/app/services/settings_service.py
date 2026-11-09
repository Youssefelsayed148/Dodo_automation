"""Key/value settings with defaults and validation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Setting
from .specs import SpecError, trim_inches

DEFAULTS: dict[str, Any] = {
    "batch_size": 10,
    "default_trim_size": "8.5x11in",
    "default_language": "en",
    "ui_language": "en",
    "concurrency": 3,
    "image_provider": "",       # empty = use IMAGE_PROVIDER env
    "cost_ceiling_usd": 0.0,    # 0 = no ceiling
    "max_redo": 2,
    "vision_qa": True,
    "manual_mode": None,        # None = auto (manual when no API key and mock images), True/False = forced
}


def _validate(key: str, value: Any) -> Any:
    if key not in DEFAULTS:
        raise ValueError(f"unknown setting '{key}'")
    if key == "batch_size":
        value = int(value)
        if value not in (5, 10):
            raise ValueError("batch_size must be 5 or 10")
    elif key in ("default_language", "ui_language"):
        if value not in ("en", "ar"):
            raise ValueError(f"{key} must be 'en' or 'ar'")
    elif key == "default_trim_size":
        try:
            trim_inches(str(value))
        except SpecError as e:
            raise ValueError(str(e)) from e
    elif key == "concurrency":
        value = int(value)
        if not 1 <= value <= 16:
            raise ValueError("concurrency must be 1-16")
    elif key == "cost_ceiling_usd":
        value = float(value)
        if value < 0:
            raise ValueError("cost_ceiling_usd must be >= 0")
    elif key == "max_redo":
        value = int(value)
        if not 0 <= value <= 5:
            raise ValueError("max_redo must be 0-5")
    elif key == "image_provider":
        from ..providers.registry import IMAGE_PROVIDERS

        if value and value not in IMAGE_PROVIDERS:
            raise ValueError(f"image_provider must be one of {IMAGE_PROVIDERS}")
    elif key == "vision_qa":
        value = bool(value)
    elif key == "manual_mode":
        if value is not None and not isinstance(value, bool):
            raise ValueError("manual_mode must be true, false or null (auto)")
    return value


def get_all(session: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in session.query(Setting).all():
        if row.key in DEFAULTS:
            out[row.key] = row.value
    return out


def get(session: Session, key: str) -> Any:
    row = session.get(Setting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def set_many(session: Session, values: dict[str, Any]) -> dict[str, Any]:
    clean = {k: _validate(k, v) for k, v in values.items()}
    for k, v in clean.items():
        row = session.get(Setting, k)
        if row is None:
            session.add(Setting(key=k, value=v))
        else:
            row.value = v
    session.commit()
    return get_all(session)
