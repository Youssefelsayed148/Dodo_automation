from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Book
from ..pdf.cover import TEMPLATES
from ..services import drive, export_prompts, settings_service, storage
from . import serialize as ser
from .common import start_job
from .deps import get_book

router = APIRouter(prefix="/api", tags=["export"])


class ExportIn(BaseModel):
    drive: bool = False
    folder_name: str | None = None
    include_unapproved: bool = False


class CoverIn(BaseModel):
    template: str | None = None
    page_id: int | None = None
    title: str | None = None
    subtitle: str | None = None


class ImportIn(BaseModel):
    text: str
    apply: bool = False


@router.post("/books/{book_id}/export")
def export(body: ExportIn = Body(default=ExportIn()), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if body.drive and not drive.is_connected():
        raise HTTPException(409, "Google Drive is not connected (Settings > Google Drive)")
    if not any(p.status == "approved" for p in book.pages) and not body.include_unapproved:
        raise HTTPException(409, "approve pages in the review step first")
    return start_job(db, "export_book", book, body.model_dump(), dedupe=False)


@router.get("/books/{book_id}/export/files")
def export_files(book: Book = Depends(get_book)):
    d = storage.export_dir(book.id)
    files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file())
    return {"files": files, "urls": {f: ser.file_url(storage.rel(d / f)) for f in files},
            "folder_preview": drive.sanitize_folder_name(book.title)}


@router.put("/books/{book_id}/cover")
def cover(body: CoverIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if data.get("template") and data["template"] not in TEMPLATES:
        raise HTTPException(422, f"template must be one of {TEMPLATES}")
    meta = dict(book.meta or {})
    meta["cover"] = {**(meta.get("cover") or {}), **data}
    if "page_id" in data:
        meta["cover"].pop("art_path", None)
    book.meta = meta
    db.commit()
    return ser.book(book, full=True)["cover"]


@router.post("/books/{book_id}/cover/art")
def cover_art(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return start_job(db, "cover_art", book)


@router.get("/books/{book_id}/cover/preview.png")
def cover_preview(book: Book = Depends(get_book)):
    import io

    from fastapi.responses import Response

    from ..pdf.cover import cover_html
    from ..render.raster import html_to_pdf_bytes, pdf_page_to_image

    img = pdf_page_to_image(html_to_pdf_bytes(cover_html(book)), 0, dpi=60)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/books/{book_id}/export/{name}")
def export_file(name: str, book: Book = Depends(get_book)):
    if name not in ("interior.pdf", "cover.pdf", "book-settings.json"):
        raise HTTPException(404, "unknown export file")
    p = storage.export_dir(book.id) / name
    if not p.is_file():
        raise HTTPException(404, "not exported yet")
    return FileResponse(p, filename=name)


# ---------------------------------------------------------- prompt export


@router.get("/books/{book_id}/prompts")
def prompts(book: Book = Depends(get_book), db: Session = Depends(get_db), batch_size: int | None = None):
    bs = batch_size or int(settings_service.get(db, "batch_size"))
    try:
        return {"planning_prompt": export_prompts.planning_prompt(db, book),
                "batches": export_prompts.page_pack(db, book, bs), "batch_size": bs,
                "brief": export_prompts.build_brief(db, book)}
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/books/{book_id}/prompts.md", response_class=PlainTextResponse)
def prompts_md(book: Book = Depends(get_book), db: Session = Depends(get_db), batch_size: int | None = None):
    bs = batch_size or int(settings_service.get(db, "batch_size"))
    md = export_prompts.export_markdown(db, book, bs)
    name = storage.safe_filename(book.title, "book")
    return PlainTextResponse(md, media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="{name}-prompts.md"'})


@router.put("/books/{book_id}/prompts/done")
def batch_done(body: dict[str, Any] = Body(...), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    meta = dict(book.meta or {})
    meta["prompt_batches_done"] = [int(x) for x in body.get("done", [])]
    book.meta = meta
    db.commit()
    return {"done": meta["prompt_batches_done"]}


@router.post("/books/{book_id}/prompts/import")
def import_plan(body: ImportIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    slots = (book.meta or {}).get("planned_slots")
    try:
        pages = export_prompts.parse_import(body.text, slots)
    except export_prompts.ImportErrorReadable as e:
        raise HTTPException(422, {"errors": e.errors})
    diff = export_prompts.diff_import(book, pages)
    if body.apply:
        export_prompts.apply_import(db, book, pages)
        return {"applied": True, "diff": diff, "pages": [ser.page(p) for p in sorted(book.pages, key=lambda p: p.index)]}
    return {"applied": False, "diff": diff}


# ------------------------------------------------------------------ drive


@router.get("/drive/status")
def drive_status():
    return {"configured": drive.is_configured(), "connected": drive.is_connected()}


def _redirect_uri(request: Request) -> str:
    return str(request.url_for("drive_callback"))


@router.get("/drive/connect")
def drive_connect(request: Request):
    try:
        url, _state = drive.auth_url(_redirect_uri(request))
    except drive.DriveError as e:
        raise HTTPException(409, str(e))
    return {"auth_url": url}


@router.get("/drive/callback", name="drive_callback", response_class=HTMLResponse)
def drive_callback(request: Request, code: str = "", error: str = ""):
    if error or not code:
        return HTMLResponse(f"<p>Google sign-in failed: {error or 'no code'}</p>", status_code=400)
    try:
        drive.finish_auth(_redirect_uri(request), code)
    except Exception as e:  # noqa: BLE001
        return HTMLResponse(f"<p>Could not finish Google sign-in: {e}</p>", status_code=400)
    front = get_settings().cors_origins[0] if get_settings().cors_origins else "/"
    return HTMLResponse(f'<p>Google Drive connected. You can close this tab.</p><p><a href="{front}/settings">Back to Dodo Book Studio</a></p>')


@router.post("/drive/disconnect")
def drive_disconnect():
    drive.disconnect()
    return {"connected": False}
