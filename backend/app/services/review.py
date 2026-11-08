"""Review grid actions (PLAN.md section 7, step 8)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Book, Page


def set_status(session: Session, page: Page, status: str) -> Page:
    if status not in ("approved", "rejected", "generated"):
        raise ValueError("review status must be approved, rejected or generated")
    if page.status in ("planned", "queued") and status != "generated":
        raise ValueError("page has not been generated yet")
    page.status = status
    session.commit()
    return page


def approve_all(session: Session, book: Book, include_failed: bool = False) -> int:
    n = 0
    for p in book.pages:
        if p.status == "generated" or (include_failed and p.status == "failed" and p.image_path):
            p.status = "approved"
            n += 1
    session.commit()
    return n


def review_summary(book: Book) -> dict:
    counts: dict[str, int] = {}
    for p in book.pages:
        counts[p.status] = counts.get(p.status, 0) + 1
    return {"counts": counts, "total": len(book.pages),
            "failed_first": [p.id for p in sorted(book.pages, key=lambda p: (p.status != "failed", p.index))]}
