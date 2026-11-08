from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import runner
from ..models import Book
from ..schemas import PageEdit
from ..services import generation, review
from ..services.characters import GateError
from . import serialize as ser
from .common import conflict, start_job
from .deps import get_book, get_page

router = APIRouter(prefix="/api/books/{book_id}", tags=["pages"])


class Redo(BaseModel):
    page_ids: list[int] | None = None
    note: str | None = None


class StatusIn(BaseModel):
    status: str


@router.get("/pages")
def list_pages(book: Book = Depends(get_book)):
    return [ser.page(p) for p in sorted(book.pages, key=lambda p: p.index)]


@router.get("/pages/{page_id}")
def get_one(page_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return ser.page(get_page(book, page_id, db))


@router.patch("/pages/{page_id}")
def edit(page_id: int, body: PageEdit, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    p = get_page(book, page_id, db)
    data = body.model_dump(exclude_unset=True)
    note = data.pop("note", None)
    for k, v in data.items():
        if v is not None:
            setattr(p, k, v)
    if note is not None:
        p.meta = {**(p.meta or {}), "note": note}
    db.commit()
    return ser.page(p)


# --------------------------------------------------------------- generate


@router.post("/generate")
def start(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    try:
        generation.ensure_ready(db, book)
    except GateError as e:
        raise conflict(e)
    existing = runner.active_job(db, book.id, "generate_pages")
    if existing:
        return ser.job(existing)
    generation.queue_pages(db, book)
    return start_job(db, "generate_pages", book)


@router.post("/generate/cancel")
def cancel(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    j = runner.active_job(db, book.id, "generate_pages")
    if j is None:
        raise HTTPException(404, "no generation running")
    return ser.job(runner.cancel(db, j.id))


@router.get("/generate/status")
def status(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    from sqlalchemy import select

    from ..models import Job

    j = db.scalar(select(Job).where(Job.book_id == book.id, Job.type == "generate_pages").order_by(Job.id.desc()))
    counts: dict[str, int] = {}
    for p in book.pages:
        counts[p.status] = counts.get(p.status, 0) + 1
    redos = sum(max(0, (p.attempts or 0) - 1) for p in book.pages)
    return {"job": ser.job(j) if j else None, "counts": counts, "redos": redos, "total": len(book.pages)}


@router.post("/pages/{page_id}/regenerate")
def regenerate(page_id: int, body: Redo = Body(default=Redo()), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    p = get_page(book, page_id, db)
    ids = generation.queue_pages(db, book, page_ids=[p.id], note=body.note)
    return start_job(db, "generate_pages", book, {"page_ids": ids}, dedupe=False)


# ----------------------------------------------------------------- review


@router.post("/pages/{page_id}/review")
def set_review(page_id: int, body: StatusIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    p = get_page(book, page_id, db)
    try:
        review.set_status(db, p, body.status)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return ser.page(p)


@router.post("/review/approve-all")
def approve_all(include_failed: bool = False, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    n = review.approve_all(db, book, include_failed)
    return {"approved": n, **review.review_summary(book)}


@router.get("/review")
def summary(book: Book = Depends(get_book)):
    return review.review_summary(book)


@router.post("/review/redo")
def redo(body: Redo = Body(default=Redo()), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    ids = generation.queue_pages(db, book, page_ids=body.page_ids, note=body.note, only_rejected=body.page_ids is None)
    if not ids:
        raise HTTPException(409, "no rejected pages to redo")
    return {"pages": ids, "job": start_job(db, "generate_pages", book, {"page_ids": ids}, dedupe=False)}
