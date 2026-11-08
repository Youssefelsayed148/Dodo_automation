from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..providers.registry import IMAGE_PROVIDERS
from ..services import compare
from .common import start_job

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareIn(BaseModel):
    providers: list[str]
    theme: str | None = None
    sheet_path: str | None = None
    scenes: list[str] | None = None


class ScoreIn(BaseModel):
    provider: str
    index: int
    scores: dict[str, int | None]


@router.post("")
def start(body: CompareIn, db: Session = Depends(get_db)):
    bad = [p for p in body.providers if p not in IMAGE_PROVIDERS]
    if bad or not body.providers:
        raise HTTPException(422, f"providers must be from {IMAGE_PROVIDERS}")
    return start_job(db, "compare_providers", None, body.model_dump())


@router.get("")
def runs():
    return compare.list_runs()


@router.get("/{run}")
def run(run: str):
    try:
        return compare.load_run(run)
    except KeyError:
        raise HTTPException(404, "run not found")


@router.put("/{run}/scores")
def scores(run: str, body: ScoreIn):
    try:
        return compare.save_scores(run, body.provider, body.index, body.scores)
    except KeyError:
        raise HTTPException(404, "run or provider not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{run}/file/{provider}/{name}")
def file(run: str, provider: str, name: str):
    root = get_settings().compare_dir.resolve()
    p = (root / run / provider / name).resolve()
    if root not in p.parents or not p.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(p)


