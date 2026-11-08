"""Interior PDF: title page, optional belongs-to, pages in order with
code-rendered page numbers, end page. Exact trim+bleed page size."""

from __future__ import annotations

from pathlib import Path

from ..models import Book
from ..render.html import document, page_fragment, seed_for
from ..render.labels import page_number
from ..schemas import is_image_type
from ..services import storage
from ..services.specs import page_spec

UNNUMBERED = ("title_page", "belongs_to_page", "end_page")


def interior_html(book: Book, include_unapproved: bool = False) -> str:
    spec = page_spec(book.trim_size, book.bleed)
    lang = book.book_language
    frags = []
    number = 0
    for p in sorted(book.pages, key=lambda p: p.index):
        if p.type not in UNNUMBERED:
            number += 1
        if is_image_type(p.type):
            if p.status != "approved" and not include_unapproved:
                continue
            path = storage.abs_path(p.image_path)
            if path is None or not path.is_file():
                continue
            frags.append(page_fragment(p.type, {}, spec, lang, image_uri=path.as_uri(),
                                       page_no=page_number(number, lang)))
        else:
            frags.append(page_fragment(p.type, p.text_content or {}, spec, lang, book_title=book.title,
                                       seed=seed_for(p.type, f"{book.id}-{p.id}"),
                                       page_no=None if p.type in UNNUMBERED else page_number(number, lang)))
    return document(frags, spec, lang, title=book.title)


def build_interior(book: Book, out: Path, include_unapproved: bool = False) -> Path:
    from weasyprint import HTML

    out.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=interior_html(book, include_unapproved), base_url=str(out.parent)).write_pdf(out)
    return out
