"""Book export: interior.pdf, cover.pdf, approved pages/, book-settings.json
into data/books/<id>/export/; optional Drive upload."""

from __future__ import annotations

import json
import shutil
from typing import Any

from sqlalchemy.orm import Session

from ..models import Book
from . import storage
from .export_prompts import build_brief, pages_as_import


def write_local_export(session: Session, book: Book, progress=lambda p, m=None: None,
                       include_unapproved: bool = False) -> dict[str, Any]:
    from ..pdf.cover import build_cover
    from ..pdf.interior import build_interior

    out = storage.export_dir(book.id)
    pages_out = out / "pages"
    shutil.rmtree(pages_out, ignore_errors=True)
    pages_out.mkdir(parents=True, exist_ok=True)
    progress(0.1, "building interior.pdf")
    build_interior(book, out / "interior.pdf", include_unapproved=include_unapproved)
    progress(0.5, "building cover.pdf")
    build_cover(book, out / "cover.pdf")
    progress(0.7, "copying pages")
    n = 0
    for p in sorted(book.pages, key=lambda p: p.index):
        if p.status != "approved" and not include_unapproved:
            continue
        src = storage.abs_path(p.image_path)
        if src and src.is_file():
            shutil.copy2(src, pages_out / f"{p.index:03d}_{p.type}.png")
            n += 1
    settings = {"brief": build_brief(session, book), "pages": pages_as_import(book),
                "cover": (book.meta or {}).get("cover") or {}}
    (out / "book-settings.json").write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    book.status = "exported"
    session.commit()
    files = sorted(str(p.relative_to(out)) for p in out.rglob("*") if p.is_file())
    return {"dir": storage.rel(out), "files": files, "pages_copied": n}
