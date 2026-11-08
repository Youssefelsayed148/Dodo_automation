from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Book, Character, Page


def get_book(book_id: int, db: Session = Depends(get_db)) -> Book:
    b = db.get(Book, book_id)
    if b is None:
        raise HTTPException(404, "book not found")
    return b


def get_character(book: Book, character_id: int, db: Session) -> Character:
    c = db.get(Character, character_id)
    if c is None or c.book_id != book.id:
        raise HTTPException(404, "character not found")
    return c


def get_page(book: Book, page_id: int, db: Session) -> Page:
    p = db.get(Page, page_id)
    if p is None or p.book_id != book.id:
        raise HTTPException(404, "page not found")
    return p
