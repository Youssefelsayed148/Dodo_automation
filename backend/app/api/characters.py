from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, Character
from ..services import characters as cs
from . import serialize as ser
from .common import conflict, start_job
from .deps import get_book, get_character

router = APIRouter(prefix="/api", tags=["characters"])


class BriefCount(BaseModel):
    count: int = Field(default=1, ge=1, le=4)


class Instruction(BaseModel):
    instruction: str = Field(min_length=1, max_length=500)


class Approve(BaseModel):
    override: bool = False


class StyleIn(BaseModel):
    rules: str | None = None


class VerdictIn(BaseModel):
    asset_id: int
    pass_: bool = Field(alias="pass")
    issues: list[str] = []

    model_config = {"populate_by_name": True}


@router.get("/books/{book_id}/characters")
def list_chars(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    chars = db.query(Character).filter(Character.book_id == book.id).order_by(Character.id).all()
    return {"characters": [ser.character(c) for c in chars], "gates": cs.gates_status(db, book),
            "style_anchor": ser.book(book)["style_anchor"]}


@router.post("/books/{book_id}/characters/briefs")
def briefs(body: BriefCount = Body(default=BriefCount()), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return start_job(db, "character_briefs", book, {"count": body.count})


@router.post("/books/{book_id}/characters")
def add_manual(fields: dict[str, Any] = Body(...), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    name = str(fields.get("name") or "").strip()
    if not name:
        raise HTTPException(422, "name is required")
    c = Character(book_id=book.id, name=name, species=str(fields.get("species", "")),
                  personality=str(fields.get("personality", "")), proportions=str(fields.get("proportions", "")),
                  signature_feature=str(fields.get("signature_feature", "")),
                  brief={"outfit": str(fields.get("outfit", "")), "versions": []})
    db.add(c)
    db.commit()
    return ser.character(c)


@router.patch("/books/{book_id}/characters/{character_id}")
def update(character_id: int, fields: dict[str, Any] = Body(...), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    return ser.character(cs.update_brief(db, c, fields))


@router.delete("/books/{book_id}/characters/{character_id}")
def delete(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    if c.in_library:
        c.book_id = None
    else:
        db.delete(c)
    db.commit()
    return {"deleted": character_id}


def _job(db, book, character_id, kind, payload=None):
    c = get_character(book, character_id, db)
    return start_job(db, kind, book, {"character_id": c.id, **(payload or {})}, dedupe=False)


@router.post("/books/{book_id}/characters/{character_id}/candidates")
def candidates(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return _job(db, book, character_id, "character_candidates")


@router.post("/books/{book_id}/characters/{character_id}/select/{asset_id}")
def select(character_id: int, asset_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    try:
        cs.select_candidate(db, book, c, asset_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return ser.character(c)


@router.post("/books/{book_id}/characters/{character_id}/edit")
def edit(character_id: int, body: Instruction, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    if cs.selected_asset(c) is None:
        raise HTTPException(409, "select a candidate first")
    return _job(db, book, character_id, "character_edit", {"instruction": body.instruction})


@router.post("/books/{book_id}/characters/{character_id}/sheet")
def sheet(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    if cs.selected_asset(c) is None:
        raise HTTPException(409, "select a candidate first")
    return _job(db, book, character_id, "character_sheet")


@router.post("/books/{book_id}/characters/{character_id}/consistency")
def consistency(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    if not any(a.kind == "sheet" for a in c.assets):
        raise HTTPException(409, "generate the character sheet first")
    return _job(db, book, character_id, "character_consistency")


@router.post("/books/{book_id}/characters/{character_id}/consistency/verdict")
def consistency_verdict(character_id: int, body: VerdictIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    """Manual mode: the user marks a test scene pass/fail."""
    c = get_character(book, character_id, db)
    try:
        cs.set_consistency_verdict(db, c, body.asset_id, body.pass_, body.issues)
    except KeyError as e:
        raise HTTPException(404, str(e))
    return ser.character(c)


@router.post("/books/{book_id}/characters/{character_id}/approve")
def approve(character_id: int, body: Approve = Body(default=Approve()), book: Book = Depends(get_book),
            db: Session = Depends(get_db)):
    c = get_character(book, character_id, db)
    try:
        cs.approve_character(db, c, body.override)
    except cs.GateError as e:
        raise conflict(e)
    return ser.character(c)


@router.post("/books/{book_id}/characters/{character_id}/unapprove")
def unapprove(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return ser.character(cs.unapprove(db, get_character(book, character_id, db)))


@router.post("/books/{book_id}/characters/{character_id}/library")
def to_library(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    try:
        return ser.character(cs.save_to_library(db, get_character(book, character_id, db)))
    except cs.GateError as e:
        raise conflict(e)


@router.get("/library")
def library(db: Session = Depends(get_db)):
    return [ser.character(c) for c in cs.library(db)]


@router.post("/books/{book_id}/characters/from-library/{character_id}")
def from_library(character_id: int, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    lib = db.get(Character, character_id)
    if lib is None:
        raise HTTPException(404, "library character not found")
    try:
        return ser.character(cs.reuse_in_book(db, book, lib))
    except cs.GateError as e:
        raise conflict(e)


@router.put("/books/{book_id}/style")
def style(body: StyleIn, book: Book = Depends(get_book), db: Session = Depends(get_db)):
    sa = cs.set_style_anchor(db, book, rules=body.rules)
    return {"rules": sa.get("rules"), "reference_url": ser.file_url(sa.get("reference_path"))}


@router.post("/books/{book_id}/sample")
def sample(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if not cs.characters_ready(db, book):
        raise HTTPException(409, "approve all characters before the sample page")
    return start_job(db, "sample_page", book)


@router.post("/books/{book_id}/sample/approve")
def approve_sample(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    try:
        cs.approve_sample(db, book)
    except cs.GateError as e:
        raise conflict(e)
    return ser.book(book, full=True)
