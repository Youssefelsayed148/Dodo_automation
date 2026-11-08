"""Source analysis: store page / pasted text / uploaded pages -> Recipe.

Originality: the model is told not to output source names, and the output is
additionally scrubbed of title/brand terms found on the page. Source images
are deleted after analysis (success or failure)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import Book, Recipe
from ..schemas import CONTENT_PAGE_TYPES, RecipeOut
from . import storage
from .llm import structured
from .url_fetch import FetchBlocked, FetchFailed, fetch_image, fetch_page

log = logging.getLogger(__name__)
STOPWORDS = {"book", "books", "coloring", "colouring", "color", "colour", "activity", "sticker", "stickers", "kids",
             "children", "for", "and", "the", "with", "pages", "page", "ages", "edition", "paperback", "amazon",
             "com", "toddlers", "girls", "boys", "fun", "easy", "big", "cute", "simple", "animals", "animal"}


def banned_terms(texts: list[str]) -> list[str]:
    """Distinctive capitalized words / phrases from titles and brands."""
    out: set[str] = set()
    for t in texts:
        if not t:
            continue
        for word in re.findall(r"[A-Z][\w'’\-]{2,}", t):
            w = word.strip("'’-")
            if w.lower() not in STOPWORDS and len(w) >= 3:
                out.add(w)
    return sorted(out, key=len, reverse=True)


def scrub(text: str, terms: list[str]) -> str:
    for term in terms:
        text = re.sub(rf"\b{re.escape(term)}\b", "", text, flags=re.I)
    return re.sub(r"\s{2,}", " ", text).replace(" ,", ",").strip()


def expected_confidence(has_uploads: bool, text_len: int, n_images: int) -> str:
    if has_uploads:
        return "high"
    if text_len < 40 and n_images == 0:
        return "low"
    return "medium"


def fetch_source(book: Book) -> dict[str, Any]:
    """Fetch the store page and preview images into data/books/<id>/source/.
    Returns fetch info with a `status`: ok | thin | blocked | failed | none."""
    if not book.source_url:
        return {"status": "none"}
    try:
        info = fetch_page(book.source_url)
    except FetchBlocked as e:
        return {"status": "blocked", "error": str(e)}
    except (FetchFailed, Exception) as e:  # noqa: BLE001
        return {"status": "failed", "error": str(e)}
    saved = 0
    src = storage.source_dir(book.id)
    for i, u in enumerate(info.image_urls):
        try:
            data = fetch_image(u)
            (src / f"fetched_{i}.img").write_bytes(data)
            saved += 1
        except Exception as e:  # noqa: BLE001
            log.info("preview image skipped (%s): %s", u, e)
    d = info.as_dict()
    d["images_saved"] = saved
    d["brand_terms"] = info.brand_terms
    d["status"] = "thin" if info.is_thin and saved == 0 else "ok"
    return d


def analyze_book(session: Session, book: Book, progress=lambda p, m=None: None) -> Recipe:
    meta = dict(book.meta or {})
    fetch = meta.get("fetch") or {}
    if book.source_url and not fetch:
        progress(0.1, "fetching store page")
        fetch = fetch_source(book)
        meta["fetch"] = fetch
    src = storage.source_dir(book.id)
    try:
        images: list[bytes] = []
        uploads = sorted(src.glob("upload_*"))
        fetched = sorted(src.glob("fetched_*"))
        for p in (uploads + fetched)[:15]:
            images.append(p.read_bytes())
        text_parts = []
        if fetch.get("status") in ("ok", "thin"):
            text_parts.append("\n".join(x for x in (fetch.get("title"), fetch.get("description")) if x))
            prod = fetch.get("product") or {}
            if prod.get("description") and prod.get("description") != fetch.get("description"):
                text_parts.append(str(prod["description"]))
        if book.source_text:
            text_parts.append(book.source_text)
        source_text = "\n\n".join(t for t in text_parts if t).strip()[:8000]
        conf = expected_confidence(bool(uploads), len(source_text), len(images))
        progress(0.4, "analyzing")
        out = structured(
            "analyze_source",
            {"source_text": source_text or "(no text available)", "image_count": len(images),
             "expected_confidence": conf, "page_types": ", ".join(CONTENT_PAGE_TYPES)},
            RecipeOut,
            images=images or None,
        )
        terms = banned_terms(list(fetch.get("brand_terms") or []) + [fetch.get("title") or ""])
        mix = [m for m in out.page_mix if m.type in CONTENT_PAGE_TYPES]
        total = sum(m.share for m in mix) or 0
        page_mix = [{"type": m.type, "share": round(m.share * 100 / total)} for m in mix] if total else []
        order = {"high": 2, "medium": 1, "low": 0}
        final_conf = out.confidence if order[out.confidence] < order[conf] else conf
        recipe = book.recipe or Recipe(book_id=book.id)
        recipe.mood = scrub(out.mood, terms)
        recipe.age_group = scrub(out.age_group, terms)
        recipe.line_weight = scrub(out.line_weight, terms)
        recipe.detail_level = scrub(out.detail_level, terms)
        recipe.page_mix = page_mix
        recipe.confidence = final_conf
        recipe.notes = scrub(out.notes, terms)
        if book.recipe is None:
            session.add(recipe)
            book.recipe = recipe
        meta["analysis"] = {"images_used": len(images), "text_chars": len(source_text)}
        meta.pop("fetch_brand_terms", None)
        book.meta = meta
        if book.status == "draft":
            book.status = "analyzed"
        session.commit()
        return recipe
    finally:
        cleanup_source_images(book.id)


def cleanup_source_images(book_id: int) -> int:
    src = storage.source_dir(book_id)
    n = 0
    for p in list(src.iterdir()):
        if p.is_file():
            p.unlink(missing_ok=True)
            n += 1
    return n


def save_upload_images(book_id: int, images: list[tuple[bytes, str]]) -> list[Path]:
    src = storage.source_dir(book_id)
    existing = len(list(src.glob("upload_*")))
    out = []
    for i, (data, ext) in enumerate(images):
        p = src / f"upload_{existing + i:03d}.{ext}"
        p.write_bytes(data)
        out.append(p)
    return out


def recipe_text(r: Recipe | None) -> str:
    if r is None:
        return "(no recipe)"
    mix = ", ".join(f"{m['type']} {m['share']}%" for m in (r.page_mix or []))
    return (f"mood: {r.mood}\nage group: {r.age_group}\nline weight: {r.line_weight}\n"
            f"detail level: {r.detail_level}\npage mix: {mix or 'n/a'}\nnotes: {r.notes}")
