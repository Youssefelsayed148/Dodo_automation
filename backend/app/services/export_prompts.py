"""Book Brief (single source of truth) + manual prompt export and import
(PLAN.md sections 2 and 15)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from ..models import Book, Character, Page
from ..schemas import CODE_PAGE_TYPES, IMAGE_PAGE_TYPES, PageType, is_image_type
from .analysis import recipe_text
from .characters import describe, style_anchor
from .planning import chosen_format, chosen_theme, content_slots, front_back_matter
from .prompts import NO_TEXT_RULE, ORIGINALITY_RULE, render
from .specs import page_spec

# ------------------------------------------------------------------ brief


def build_brief(session: Session, book: Book) -> dict[str, Any]:
    theme = chosen_theme(book)
    fmt = chosen_format(book)
    chars = session.query(Character).filter(Character.book_id == book.id).order_by(Character.id).all()
    rules, _ = style_anchor(book)
    spec = page_spec(book.trim_size, book.bleed)
    fetch = (book.meta or {}).get("fetch") or {}
    source_desc = "\n".join(x for x in [fetch.get("description") or "", book.source_text or ""] if x).strip()
    r = book.recipe
    return {
        "title": book.title,
        "book_language": book.book_language,
        "recipe": None if r is None else {"mood": r.mood, "age_group": r.age_group, "line_weight": r.line_weight,
                                          "detail_level": r.detail_level, "page_mix": r.page_mix,
                                          "confidence": r.confidence, "notes": r.notes},
        "recipe_text": recipe_text(r),
        "source_description": source_desc,
        "theme": None if theme is None else {"title": theme.title, "description": theme.description},
        "format": None if fmt is None else {"name": fmt.name, "blocks": fmt.blocks, "description": fmt.description},
        "characters": [{"name": c.name, "species": c.species, "personality": c.personality,
                        "proportions": c.proportions, "signature_feature": c.signature_feature,
                        "outfit": (c.brief or {}).get("outfit", ""), "status": c.status} for c in chars],
        "line_art_rules": rules,
        "specs": {**spec.as_dict(), "page_count": book.page_count},
        "originality_rule": ORIGINALITY_RULE,
        "no_text_rule": NO_TEXT_RULE,
    }


def brief_text(brief: dict[str, Any]) -> str:
    lines = [f"BOOK: {brief['title']}", f"BOOK LANGUAGE: {'Arabic' if brief['book_language'] == 'ar' else 'English'}", "",
             "STYLE FORMULA (from a book I like; reuse only this abstract formula):", brief["recipe_text"], ""]
    if brief.get("source_description"):
        lines += ["STORE DESCRIPTION OF THE LIKED BOOK (for mood only, do not copy names or text):",
                  brief["source_description"][:3000], ""]
    if brief.get("theme"):
        lines += [f"THEME: {brief['theme']['title']} - {brief['theme']['description']}", ""]
    if brief.get("format"):
        mix = ", ".join(f"{b['type']} {b['share']}%" for b in brief["format"]["blocks"])
        lines += [f"FORMAT: {brief['format']['name']} ({mix})", ""]
    if brief.get("characters"):
        lines.append("CHARACTERS:")
        for c in brief["characters"]:
            lines.append(f"- {c['name']}: {c['species']}; proportions: {c['proportions']}; signature feature: "
                         f"{c['signature_feature']}; outfit: {c['outfit'] or 'none'}; personality: {c['personality']}")
        lines.append("")
    s = brief["specs"]
    lines += ["LINE-ART RULES:", brief["line_art_rules"], "",
              f"SPECS: trim {s['trim']} ({s['trim_in'][0]:.2f} x {s['trim_in'][1]:.2f} in), bleed {'on' if s['bleed'] else 'off'}, "
              f"{s['dpi']} DPI ({s['pixels'][0]} x {s['pixels'][1]} px per page), {s['page_count']} pages total", "",
              brief["originality_rule"], brief["no_text_rule"]]
    return "\n".join(lines)


# ---------------------------------------------------------- import schema


class ImportedPage(BaseModel):
    index: int | None = None
    type: PageType
    description: str = Field(min_length=1)
    characters: list[str] = []
    prompt: str = ""
    text_content: dict[str, Any] = {}


class ImportedPlan(BaseModel):
    pages: list[ImportedPage] = Field(min_length=1)


def planning_prompt(session: Session, book: Book) -> str:
    fmt = chosen_format(book)
    slots = content_slots(book, fmt) if fmt else []
    brief = build_brief(session, book)
    return render("planning_prompt_export", {
        "brief": brief_text(brief),
        "page_count": len(slots),
        "slots_json": json.dumps([{"index": i + 1, "type": t} for i, t in enumerate(slots)]),
        "schema": json.dumps(ImportedPlan.model_json_schema()),
    })


def page_pack(session: Session, book: Book, batch_size: int) -> list[dict[str, Any]]:
    """Per-batch messages for manual image generation (image pages only)."""
    if batch_size not in (5, 10):
        raise ValueError("batch size must be 5 or 10")
    chars = session.query(Character).filter(Character.book_id == book.id).order_by(Character.id).all()
    rules, _ = style_anchor(book)
    pages = [p for p in sorted(book.pages, key=lambda p: p.index) if is_image_type(p.type)]
    header_chars = "\n".join(f"- {describe(c)}" for c in chars) or "- (no recurring characters)"
    spec = page_spec(book.trim_size, book.bleed)
    w, h = spec.pixel_size
    header = (f"Create black-and-white coloring book pages, one image per numbered item below.\n"
              f"Style rules: {rules}\nCharacters (use the attached character sheet; keep them identical):\n{header_chars}\n"
              f"Portrait page, aspect {w}:{h}. No text, letters or numbers inside the images.")
    batches = []
    for i in range(0, len(pages), batch_size):
        chunk = pages[i:i + batch_size]
        items = []
        for p in chunk:
            prompt = p.prompt or p.description
            items.append(f"{p.index}. [{p.type}] {prompt}")
        batches.append({"batch": i // batch_size + 1, "page_ids": [p.id for p in chunk],
                        "page_indexes": [p.index for p in chunk], "text": header + "\n\n" + "\n".join(items)})
    return batches


def export_markdown(session: Session, book: Book, batch_size: int) -> str:
    parts = [f"# {book.title} - prompts", "", "## Planning prompt", "", "```", planning_prompt(session, book), "```", ""]
    for b in page_pack(session, book, batch_size):
        parts += [f"## Page batch {b['batch']} (pages {', '.join(map(str, b['page_indexes']))})", "", "```", b["text"], "```", ""]
    return "\n".join(parts)


# ----------------------------------------------------------------- import


_NUMBERED = re.compile(r"^\s*(\d+)[.)\-:]\s*(?:\[(\w+)\])?\s*(.+?)\s*$")


class ImportErrorReadable(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _readable(e: ValidationError) -> list[str]:
    out = []
    for err in e.errors():
        loc = err.get("loc", ())
        where = []
        if len(loc) >= 2 and loc[0] == "pages" and isinstance(loc[1], int):
            where.append(f"page {loc[1] + 1}")
            loc = loc[2:]
        if loc:
            where.append(".".join(str(x) for x in loc))
        msg = err.get("msg", "invalid")
        if err.get("type") == "literal_error":
            msg = "unknown page type (allowed: " + ", ".join(IMAGE_PAGE_TYPES + CODE_PAGE_TYPES) + ")"
        out.append(f"{' / '.join(where) or 'input'}: {msg}")
    return out


def parse_import(text: str, default_types: list[str] | None = None) -> list[ImportedPage]:
    """Accept the JSON object/array from a chat, or a numbered list
    ("1. [scene] description")."""
    from ..providers.jsonutil import JSONExtractError, extract_json

    text = (text or "").strip()
    if not text:
        raise ImportErrorReadable(["nothing to import"])
    data: Any = None
    try:
        data = extract_json(text)
    except JSONExtractError:
        data = None
    if data is not None:
        if isinstance(data, list):
            data = {"pages": data}
        try:
            return ImportedPlan.model_validate(data).pages
        except ValidationError as e:
            raise ImportErrorReadable(_readable(e)) from e
    pages = []
    for line in text.splitlines():
        m = _NUMBERED.match(line)
        if not m:
            continue
        n, t, desc = int(m.group(1)), m.group(2), m.group(3)
        if t is None:
            t = (default_types[n - 1] if default_types and 0 < n <= len(default_types) else "scene")
        try:
            pages.append(ImportedPage(index=n, type=t, description=desc, prompt=desc if is_image_type(t) else ""))
        except ValidationError as e:
            raise ImportErrorReadable([f"line {n}: " + x for x in _readable(e)]) from e
    if not pages:
        raise ImportErrorReadable(["no JSON and no numbered lines found"])
    return pages


def diff_import(book: Book, pages: list[ImportedPage]) -> dict[str, Any]:
    content = [p for p in sorted(book.pages, key=lambda p: p.index) if p.type not in ("title_page", "belongs_to_page", "end_page")]
    rows = []
    for i in range(max(len(content), len(pages))):
        old = content[i] if i < len(content) else None
        new = pages[i] if i < len(pages) else None
        change = "same"
        if old is None:
            change = "added"
        elif new is None:
            change = "removed"
        elif old.type != new.type or old.description != new.description or (new.prompt and new.prompt != old.prompt) \
                or (new.text_content and new.text_content != old.text_content):
            change = "changed"
        rows.append({"n": i + 1, "change": change,
                     "old": None if old is None else {"type": old.type, "description": old.description},
                     "new": None if new is None else {"type": new.type, "description": new.description}})
    return {"rows": rows, "changed": sum(1 for r in rows if r["change"] != "same")}


def apply_import(session: Session, book: Book, pages: list[ImportedPage]) -> list[Page]:
    chars = session.query(Character).filter(Character.book_id == book.id).all()
    by_name = {c.name.lower(): c.id for c in chars}
    for old in list(book.pages):
        session.delete(old)
    session.flush()
    front, back = front_back_matter(book)
    rows, idx = [], 1
    for t in front:
        rows.append(Page(book_id=book.id, index=idx, type=t, description=t.replace("_", " ")))
        idx += 1
    for p in pages:
        if p.type in ("title_page", "belongs_to_page", "end_page"):
            continue
        rows.append(Page(book_id=book.id, index=idx, type=p.type, description=p.description.strip(),
                         prompt=p.prompt or "", text_content=p.text_content or {},
                         meta={"characters": [by_name[n.lower()] for n in p.characters if n.lower() in by_name],
                               "character_names": p.characters, "imported": True}))
        idx += 1
    for t in back:
        rows.append(Page(book_id=book.id, index=idx, type=t, description=t.replace("_", " ")))
        idx += 1
    session.add_all(rows)
    book.page_count = len(rows)
    session.commit()
    return rows


def pages_as_import(book: Book) -> list[dict[str, Any]]:
    """The current plan in import format (used for round-trip tests/export)."""
    out = []
    for p in sorted(book.pages, key=lambda p: p.index):
        if p.type in ("title_page", "belongs_to_page", "end_page"):
            continue
        out.append({"index": len(out) + 1, "type": p.type, "description": p.description,
                    "characters": (p.meta or {}).get("character_names", []), "prompt": p.prompt or "",
                    "text_content": p.text_content or {}})
    return out
