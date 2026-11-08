"""Code-drawn pages: maze, dot_to_dot, word_search, trace_write, qa_page,
story_text, title_page, belongs_to_page, end_page. No image model involved."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..services.specs import PageSpec
from .html import document, page_fragment, seed_for
from .raster import render_html_page_png

CODE_RENDERED = ("maze", "dot_to_dot", "word_search", "trace_write", "qa_page", "story_text",
                 "title_page", "belongs_to_page", "end_page")


def render_code_page(page_type: str, content: dict[str, Any], spec: PageSpec, lang: str, out: Path, *,
                     book_title: str = "", seed_key: Any = "") -> Path:
    """Render one code page to a print-size PNG and return its path."""
    frag = page_fragment(page_type, content, spec, lang, book_title=book_title, seed=seed_for(page_type, seed_key))
    html = document([frag], spec, lang, title=book_title)
    return render_html_page_png(html, out, spec.pixel_size, spec.dpi)
