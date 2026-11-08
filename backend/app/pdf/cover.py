"""Front cover (v1): title as live text over chosen art. Templates:
classic (title on top), framed (rounded frame), band (title in a bottom band)."""

from __future__ import annotations

from html import escape
from pathlib import Path

from ..models import Book
from ..render.html import ARABIC, LATIN_DISPLAY, font_face_css
from ..services import storage
from ..services.specs import page_spec

TEMPLATES = ("classic", "framed", "band")


def cover_art_path(book: Book) -> Path | None:
    cover = (book.meta or {}).get("cover") or {}
    if cover.get("art_path"):
        p = storage.abs_path(cover["art_path"])
        if p and p.is_file():
            return p
    page_id = cover.get("page_id")
    pages = sorted(book.pages, key=lambda p: p.index)
    candidates = [p for p in pages if p.id == page_id] or [p for p in pages if p.type in ("scene", "single_character") and p.image_path]
    for p in candidates:
        path = storage.abs_path(p.image_path)
        if path and path.is_file():
            return path
    return None


def cover_html(book: Book) -> str:
    spec = page_spec(book.trim_size, book.bleed)
    cover = (book.meta or {}).get("cover") or {}
    template = cover.get("template", "classic")
    if template not in TEMPLATES:
        template = "classic"
    lang = book.book_language
    d = "rtl" if lang == "ar" else "ltr"
    font = ARABIC if lang == "ar" else LATIN_DISPLAY
    title = escape(cover.get("title") or book.title)
    subtitle = escape(cover.get("subtitle") or "")
    art = cover_art_path(book)
    w, h = spec.page_width_in, spec.page_height_in
    pad = spec.bleed_in + 0.5
    art_h = max(1.0, h - 2 * pad - (3.4 if template == "framed" else 2.8))
    art_html = f'<img class="art" src="{art.as_uri()}"/>' if art else '<div class="art"></div>'
    css = f"""
{font_face_css()}
@page {{ size: {w}in {h}in; margin: 0; }}
html, body {{ margin: 0; }}
body {{ font-family: {font}; }}
.cover {{ width: {w}in; height: {h}in; padding: {pad}in; box-sizing: border-box; display: block;
          background: #fff; position: relative; overflow: hidden; }}
.title {{ font-size: 44pt; font-weight: 700; text-align: center; line-height: 1.15; margin: 0; }}
.subtitle {{ font-size: 18pt; text-align: center; margin-top: 0.15in; }}
.art {{ height: {art_h:.3f}in; width: 100%; object-fit: contain; margin: 0.3in 0; display: block; }}
.framed {{ border: 4pt solid #000; border-radius: 22pt; padding: 0.35in; height: {h - 2 * pad:.3f}in; box-sizing: border-box; }}
.band {{ background: #000; color: #fff; padding: 0.3in; border-radius: 16pt; }}
"""
    head = f'<h1 class="title">{title}</h1>' + (f'<div class="subtitle">{subtitle}</div>' if subtitle else "")
    if template == "framed":
        body = f'<div class="framed">{head}{art_html}</div>'
    elif template == "band":
        body = f'{art_html}<div class="band">{head}</div>'
    else:
        body = f"{head}{art_html}"
    return (f'<!doctype html><html lang="{lang}" dir="{d}"><head><meta charset="utf-8"><style>{css}</style></head>'
            f'<body><section class="cover" lang="{lang}" dir="{d}">{body}</section></body></html>')


def build_cover(book: Book, out: Path) -> Path:
    from weasyprint import HTML

    out.parent.mkdir(parents=True, exist_ok=True)
    from ..render.raster import PDF_LOCK

    with PDF_LOCK:
        HTML(string=cover_html(book), base_url=str(out.parent)).write_pdf(out)
    return out
