from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..jobs import runner
from ..models import Book
from . import serialize as ser


def start_job(db: Session, job_type: str, book: Book | None, payload: dict[str, Any] | None = None,
              dedupe: bool = True) -> dict[str, Any]:
    if book is not None and dedupe:
        existing = runner.active_job(db, book.id, job_type)
        if existing is not None:
            return ser.job(existing)
    job = runner.enqueue(db, job_type, {**(payload or {}), **({"book_id": book.id} if book else {})},
                         book_id=book.id if book else None)
    return ser.job(job)


def conflict(e: Exception) -> HTTPException:
    return HTTPException(409, str(e))
