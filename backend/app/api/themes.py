from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book
from ..schemas import FormatBlocksIn
from ..services import planning
from . import serialize as ser
from .common import start_job
from .deps import get_book

router = APIRouter(prefix="/api/books/{book_id}", tags=["themes"])


class ChooseTheme(BaseModel):
    theme_id: int
    title: str | None = None


class Rename(BaseModel):
    title: str


class Hybrid(BaseModel):
    instruction: str


@router.post("/themes/propose")
def propose_themes(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if book.recipe is None:
        raise HTTPException(409, "analyze the source (or fill the style) first")
    return start_job(db, "propose_themes", book)


@router.get("/themes")
def themes(book: Book = Depends(get_book)):
    return [ser.theme(t) for t in book.themes]


@router.post("/themes/choose")
def choose_theme(body: ChooseTheme, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    try:
        planning.choose_theme(db, book, body.theme_id, body.title)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return ser.book(book, full=True)


@router.post("/title")
def rename(body: Rename, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    t = body.title.strip()
    if not t:
        raise HTTPException(422, "title cannot be empty")
    book.title = t
    th = planning.chosen_theme(book)
    if th:
        th.title = t
    db.commit()
    return ser.book(book, full=True)


@router.post("/formats/propose")
def propose_formats(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if planning.chosen_theme(book) is None:
        raise HTTPException(409, "choose a theme first")
    return start_job(db, "propose_formats", book)


@router.post("/formats/hybrid")
def hybrid(body: Hybrid, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if not body.instruction.strip():
        raise HTTPException(422, "describe the hybrid you want")
    return start_job(db, "propose_formats", book, {"instruction": body.instruction.strip()}, dedupe=False)


@router.get("/formats")
def formats(book: Book = Depends(get_book)):
    return [ser.fmt(f) for f in book.formats]


@router.post("/formats/{format_id}/choose")
def choose_format(format_id: int, body: FormatBlocksIn | None = Body(default=None), book: Book = Depends(get_book),
                  db: Session = Depends(get_db)):
    try:
        planning.choose_format(db, book, format_id, [b.model_dump() for b in body.blocks] if body else None)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return ser.book(book, full=True)


@router.put("/formats/{format_id}")
def edit_format(format_id: int, body: FormatBlocksIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    f = next((f for f in book.formats if f.id == format_id), None)
    if f is None:
        raise HTTPException(404, "format not found")
    try:
        planning.set_blocks(f, [b.model_dump() for b in body.blocks])
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return ser.fmt(f)


@router.post("/plan")
def plan(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if planning.chosen_format(book) is None:
        raise HTTPException(409, "choose a format first")
    return start_job(db, "plan_pages", book)


@router.get("/plan/preview")
def plan_preview(book: Book = Depends(get_book)):
    f = planning.chosen_format(book)
    if f is None:
        return {"slots": []}
    front, back = planning.front_back_matter(book)
    return {"slots": front + planning.content_slots(book, f) + back}
