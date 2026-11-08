"""HTML/CSS for code-drawn pages and the PDF documents (WeasyPrint).

WeasyPrint (Pango/HarfBuzz) shapes Arabic correctly; every element carries
`lang` and `dir` so direction is explicit.
"""

from __future__ import annotations

import hashlib
from html import escape
from pathlib import Path
from typing import Any

from ..services.specs import SAFE_MARGIN_IN, PageSpec
from . import dot_to_dot, maze, word_search
from .labels import label

FONTS_DIR = Path(__file__).resolve().parent.parent / "pdf" / "fonts"

# family name -> candidate files (bundled by scripts/fetch_fonts.py)
FONT_FILES = {
    "Fredoka": ["Fredoka-Variable.ttf", "Fredoka-SemiBold.ttf", "Fredoka-Regular.ttf"],
    "Nunito": ["Nunito-Variable.ttf", "Nunito-Regular.ttf"],
    "Noto Naskh Arabic": ["NotoNaskhArabic-Variable.ttf", "NotoNaskhArabic-Regular.ttf"],
    "Cairo": ["Cairo-Variable.ttf", "Cairo-Regular.ttf"],
}
LATIN_DISPLAY = '"Fredoka", "Nunito", "DejaVu Sans", sans-serif'
LATIN_BODY = '"Nunito", "DejaVu Sans", sans-serif'
ARABIC = '"Noto Naskh Arabic", "Cairo", "DejaVu Sans", sans-serif'


def font_face_css() -> str:
    out = []
    for family, files in FONT_FILES.items():
        for f in files:
            p = FONTS_DIR / f
            if p.is_file():
                out.append(f'@font-face {{ font-family: "{family}"; src: url("{p.as_uri()}"); }}')
                break
    return "\n".join(out)


def seed_for(*parts: Any) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def base_css(spec: PageSpec, lang: str) -> str:
    w, h = spec.page_width_in, spec.page_height_in
    pad = spec.bleed_in + SAFE_MARGIN_IN
    body_font = ARABIC if lang == "ar" else LATIN_BODY
    display_font = ARABIC if lang == "ar" else LATIN_DISPLAY
    return f"""
{font_face_css()}
@page {{ size: {w}in {h}in; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font-family: {body_font}; color: #000; }}
.page {{ width: {w}in; height: {h}in; padding: {pad}in; position: relative; overflow: hidden;
        page-break-after: always; display: flex; flex-direction: column; }}
.page:last-child {{ page-break-after: auto; }}
.page-title {{ font-family: {display_font}; font-size: 30pt; text-align: center; margin: 0 0 0.25in; font-weight: 600; }}
.fill {{ flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; }}
.fill svg {{ width: 100%; height: 100%; }}
.fill img {{ max-width: 100%; max-height: 100%; }}
/* plain block layout: WeasyPrint misplaces column flex items in RTL */
.col {{ flex: 1; display: block; text-align: center; }}
.col.centered {{ padding-top: 2.6in; }}
.pageno {{ position: absolute; bottom: {spec.bleed_in + 0.25}in; left: 0; right: 0; text-align: center; font-size: 11pt; }}
.story {{ font-size: 22pt; line-height: 1.6; text-align: start; }}
.qa-q {{ font-size: 22pt; margin-bottom: 0.4in; }}
.qa-choice {{ font-size: 18pt; margin: 0.18in 0; display: flex; align-items: center; gap: 0.2in; }}
.box {{ width: 0.3in; height: 0.3in; border: 2pt solid #000; border-radius: 4pt; flex: none; }}
.line {{ border-bottom: 1.5pt solid #000; height: 0.55in; }}
.trace {{ font-family: {display_font}; font-size: 72pt; color: #b5b5b5; line-height: 1.5;
         border-bottom: 1.5pt dashed #000; text-align: center; }}
.write {{ height: 1.1in; border-bottom: 1.5pt solid #000; }}
table.ws {{ border-collapse: collapse; margin: 0 auto; }}
table.ws td {{ width: var(--cell); height: var(--cell); text-align: center; vertical-align: middle;
              font-size: 15pt; font-family: {body_font}; border: 0.6pt solid #000; }}
table.ws td.hit {{ outline: 2pt solid #000; outline-offset: -3pt; }}
.wordlist {{ margin-top: 0.3in; display: flex; flex-wrap: wrap; gap: 0.12in 0.35in; justify-content: center; font-size: 15pt; }}
.title-main {{ font-family: {display_font}; font-size: 46pt; text-align: center; font-weight: 700; line-height: 1.2; }}
.title-sub {{ font-size: 16pt; text-align: center; margin-top: 0.3in; }}
.frame {{ border: 3pt solid #000; border-radius: 18pt; padding: 0.5in; width: 100%; text-align: center; }}
.name-line {{ border-bottom: 2pt solid #000; height: 0.8in; margin-top: 0.4in; }}
.image-page {{ padding: 0; }}
.image-page img {{ width: 100%; height: 100%; object-fit: contain; display: block; }}
"""


def _title(text: str) -> str:
    return f'<h1 class="page-title">{escape(text)}</h1>' if text else ""


def drawing_area_in(spec: PageSpec, title: bool = True) -> tuple[float, float]:
    pad = spec.bleed_in + SAFE_MARGIN_IN
    w = spec.page_width_in - 2 * pad
    h = spec.page_height_in - 2 * pad - (0.9 if title else 0)
    return w, h


def page_fragment(page_type: str, content: dict[str, Any], spec: PageSpec, lang: str, *,
                  book_title: str = "", seed: int = 0, page_no: str | None = None,
                  image_uri: str | None = None) -> str:
    """Return one `<section class="page">` for any page type."""
    d = 'rtl' if lang == "ar" else 'ltr'
    num = f'<div class="pageno">{escape(page_no)}</div>' if page_no else ""
    c = content or {}
    if image_uri is not None:
        return f'<section class="page image-page" lang="{lang}" dir="{d}"><img src="{escape(image_uri)}"/>{num}</section>'
    t = page_type
    body = ""
    if t == "maze":
        w, h = drawing_area_in(spec)
        m = maze.for_page(c.get("difficulty", "easy"), w / max(h, 0.1), seed=seed)
        body = _title(c.get("title") or label(lang, "maze")) + f'<div class="fill">{maze.to_svg(m, w * 100, h * 100, stroke=6)}</div>'
    elif t == "dot_to_dot":
        w, h = drawing_area_in(spec)
        font = "Noto Naskh Arabic" if lang == "ar" else "DejaVu Sans"
        body = _title(c.get("title") or label(lang, "dot_to_dot")) + f'<div class="fill">{dot_to_dot.to_svg(c.get("shape", "star"), w * 100, h * 100, font)}</div>'
    elif t == "word_search":
        words = c.get("words") or []
        ws = word_search.generate(words, lang, c.get("difficulty", "easy"), seed=seed)
        w, _ = drawing_area_in(spec)
        cell_mm = min(14.0, (w * 25.4) / ws.size)
        listing = "".join(f"<span>{escape(p.word if lang == 'ar' else p.word)}</span>" for p in ws.placements)
        body = (_title(c.get("title") or label(lang, "word_search")) + f'<div class="col">'
                f'{word_search.to_html(ws, cell_mm)}<div class="wordlist">{listing}</div></div>')
    elif t == "trace_write":
        text = str(c.get("text", ""))
        body = (_title(label(lang, "trace_write")) +
                "".join(f'<div class="trace">{escape(text)}</div><div class="write"></div>' for _ in range(3)))
    elif t == "qa_page":
        q = escape(str(c.get("question", "")))
        choices = c.get("choices") or []
        if choices:
            items = "".join(f'<div class="qa-choice"><span class="box"></span><span>{escape(str(ch))}</span></div>' for ch in choices)
        else:
            items = '<div class="line"></div>' * 5
        body = _title(label(lang, "qa_page")) + f'<div class="qa-q">{q}</div>{items}'
    elif t == "story_text":
        paras = "".join(f"<p>{escape(p)}</p>" for p in str(c.get("text", "")).split("\n") if p.strip())
        body = f'<div class="fill"><div class="story">{paras}</div></div>'
    elif t == "title_page":
        body = (f'<div class="col centered"><div class="title-main">{escape(book_title)}</div>'
                f'<div class="title-sub">{escape(str(c.get("subtitle", "")))}</div></div>')
    elif t == "belongs_to_page":
        body = (f'<div class="col centered"><div class="frame"><div class="title-main" style="font-size:30pt">'
                f'{escape(label(lang, "belongs_to"))}</div><div class="name-line"></div></div></div>')
    elif t == "end_page":
        body = (f'<div class="col centered"><div class="title-main">{escape(label(lang, "the_end"))}</div>'
                f'<div class="title-sub">{escape(c.get("note") or label(lang, "end_note"))}</div></div>')
    else:
        raise ValueError(f"no code renderer for page type '{t}'")
    return f'<section class="page" lang="{lang}" dir="{d}">{body}{num}</section>'


def document(fragments: list[str], spec: PageSpec, lang: str, title: str = "", extra_css: str = "") -> str:
    d = 'rtl' if lang == "ar" else 'ltr'
    return (f'<!doctype html><html lang="{lang}" dir="{d}"><head><meta charset="utf-8"><title>{escape(title)}</title>'
            f'<style>{base_css(spec, lang)}{extra_css}</style></head><body>{"".join(fragments)}</body></html>')
