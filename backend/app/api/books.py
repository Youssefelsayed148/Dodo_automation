from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, Recipe
from ..schemas import BookCreate, BookUpdate, RecipeIn
from ..services import analysis, backup, settings_service, storage, uploads, usage
from ..services.specs import SpecError, page_spec
from ..services.url_fetch import FetchBlocked, validate_url
from . import serialize as ser
from .common import start_job
from .deps import get_book

router = APIRouter(prefix="/api/books", tags=["books"])


@router.get("")
def list_books(db: Session = Depends(get_db)):
    return [ser.book(b) for b in db.scalars(select(Book).order_by(Book.id.desc())).all()]


@router.post("")
def create_book(body: BookCreate, db: Session = Depends(get_db)):
    s = settings_service.get_all(db)
    b = Book(title=body.title or "Untitled book", book_language=body.book_language or s["default_language"],
             trim_size=body.trim_size or s["default_trim_size"], meta={"belongs_to": True})
    db.add(b)
    db.commit()
    db.refresh(b)
    return ser.book(b, full=True)


@router.get("/{book_id}")
def get_one(book: Book = Depends(get_book)):
    return ser.book(book, full=True)


@router.patch("/{book_id}")
def update_book(body: BookUpdate, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    if "trim_size" in data:
        try:
            page_spec(data["trim_size"], data.get("bleed", book.bleed))
        except SpecError as e:
            raise HTTPException(422, str(e))
    meta_patch = data.pop("meta", None)
    for k, v in data.items():
        setattr(book, k, v)
    if meta_patch:
        allowed = {"belongs_to", "image_provider", "cover"}
        bad = set(meta_patch) - allowed
        if bad:
            raise HTTPException(422, f"meta keys not editable: {sorted(bad)}")
        if "image_provider" in meta_patch and meta_patch["image_provider"]:
            from ..providers.registry import IMAGE_PROVIDERS

            if meta_patch["image_provider"] not in IMAGE_PROVIDERS:
                raise HTTPException(422, "unknown image provider")
        book.meta = {**(book.meta or {}), **meta_patch}
    if {"trim_size", "bleed", "page_count", "book_language"} & set(data) and book.status in ("characters", "themed"):
        book.status = "specced" if book.pages else book.status
    db.commit()
    return ser.book(book, full=True)


@router.delete("/{book_id}")
def delete_book(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    from ..models import Character

    bid = book.id
    for c in db.query(Character).filter(Character.book_id == bid, Character.in_library.is_(False)).all():
        db.delete(c)
    for c in db.query(Character).filter(Character.book_id == bid, Character.in_library.is_(True)).all():
        c.book_id = None  # keep library characters (their files stay in the book folder)
    db.delete(book)
    db.commit()
    return {"deleted": bid}


# ------------------------------------------------------------------ source


@router.post("/{book_id}/source")
async def submit_source(
    book: Book = Depends(get_book),
    db: Session = Depends(get_db),
    url: str = Form(""),
    text: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    url, text = url.strip(), text.strip()
    if url:
        try:
            validate_url(url)
        except FetchBlocked as e:
            raise HTTPException(422, str(e))
        except Exception as e:  # noqa: BLE001 - DNS failure etc. is reported by the job
            if "resolve" not in str(e):
                raise HTTPException(422, str(e))
    if len(files) > uploads.MAX_FILES:
        raise HTTPException(422, f"at most {uploads.MAX_FILES} files")
    images = []
    for f in files:
        data = await f.read()
        if not data:
            continue
        try:
            images += uploads.process_upload(data)
        except uploads.UploadError as e:
            raise HTTPException(422, f"{f.filename}: {e}")
    if not url and not text and not images:
        raise HTTPException(422, "give a store link, a description or pages")
    analysis.cleanup_source_images(book.id)
    if images:
        analysis.save_upload_images(book.id, images[:15])
    book.source_url = url or None
    book.source_text = text or None
    book.source_type = ("url_pages" if images else "url") if url else ("text" if text or images else "none")
    meta = dict(book.meta or {})
    meta.pop("fetch", None)
    book.meta = meta
    db.commit()
    job = start_job(db, "analyze_source", book, dedupe=False)
    return {"book": ser.book(book, full=True), "job": job}


@router.get("/{book_id}/recipe")
def get_recipe(book: Book = Depends(get_book)):
    return ser.recipe(book.recipe)


@router.put("/{book_id}/recipe")
def put_recipe(body: RecipeIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    r = book.recipe
    if r is None:
        r = Recipe(book_id=book.id)
        db.add(r)
        book.recipe = r
    data = body.model_dump(exclude_unset=True)
    if "page_mix" in data and data["page_mix"] is not None:
        data["page_mix"] = [{"type": m["type"], "share": m["share"]} for m in data["page_mix"]]
    for k, v in data.items():
        if v is not None:
            setattr(r, k, v)
    if book.status == "draft":
        book.status = "analyzed"
    db.commit()
    return ser.recipe(r)


# -------------------------------------------------------------- cost/backup


@router.get("/{book_id}/cost")
def cost(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    summary = usage.book_summary(db, book.id)
    summary["ceiling_usd"] = settings_service.get(db, "cost_ceiling_usd")
    return summary


@router.get("/{book_id}/backup")
def download_backup(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    blob = backup.export_zip(db, book)
    name = storage.safe_filename(book.title, "book")
    return Response(blob, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})


@router.post("/import-backup")
async def import_backup(file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read()
    if len(data) > 1024 * 1024 * 1024:
        raise HTTPException(422, "backup too large")
    try:
        b = backup.import_zip(db, data)
    except (ValueError, KeyError) as e:
        db.rollback()
        raise HTTPException(422, f"invalid backup: {e}")
    except Exception as e:  # noqa: BLE001 - zipfile.BadZipFile etc.
        db.rollback()
        raise HTTPException(422, f"invalid backup: {e}")
    return ser.book(b, full=True)
