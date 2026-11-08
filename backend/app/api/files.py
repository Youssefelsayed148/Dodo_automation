"""Serve stored images/files from the data dir (path-traversal safe), with
cached thumbnails (?thumb=1) so large review grids stay fast."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import get_settings
from ..services import storage
from ..services.cleanup import make_thumbnail

router = APIRouter(prefix="/api/files", tags=["files"])
ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".pdf", ".json"}


@router.get("/{path:path}")
def serve(path: str, thumb: int = 0):
    root = get_settings().data_dir.resolve()
    p = (root / path).resolve()
    if root not in p.parents or not p.is_file() or p.suffix.lower() not in ALLOWED:
        raise HTTPException(404, "file not found")
    if p.name == "google_token.json" or p.parent == root:
        raise HTTPException(404, "file not found")
    if thumb and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
        t = storage.thumb_for(storage.rel(p))
        if not t.is_file() or t.stat().st_mtime < p.stat().st_mtime:
            make_thumbnail(p, t)
        return FileResponse(t, headers={"Cache-Control": "max-age=60"})
    return FileResponse(p, headers={"Cache-Control": "no-cache"})


