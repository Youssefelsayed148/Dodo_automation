from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..providers.registry import available_image_providers
from ..services import drive, settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_all(db: Session = Depends(get_db)):
    s = get_settings()
    return {"values": settings_service.get_all(db), "defaults": settings_service.DEFAULTS,
            "providers": {"image": available_image_providers(), "env_image_provider": s.image_provider,
                          "text": s.text_provider, "vision": s.vision_provider, "text_model": s.anthropic_model if s.text_provider == "anthropic" else "mock"},
            "drive": {"configured": drive.is_configured(), "connected": drive.is_connected()}}


@router.put("")
def put(values: dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    try:
        return {"values": settings_service.set_many(db, values)}
    except ValueError as e:
        raise HTTPException(422, str(e))
