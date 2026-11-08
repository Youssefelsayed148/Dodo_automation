"""Themes, formats and the page plan (PLAN.md sections 7.3-7.4, 8)."""

from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy.orm import Session

from ..models import Book, Character, FormatOption, Page, ThemeOption
from ..schemas import CONTENT_PAGE_TYPES, FormatsOut, PagePlanOut, ThemesOut, is_image_type
from .analysis import recipe_text
from .llm import LLMOutputError, structured

# ------------------------------------------------------------------ themes


def chosen_theme(book: Book) -> ThemeOption | None:
    return next((t for t in book.themes if t.chosen), None)


def chosen_format(book: Book) -> FormatOption | None:
    return next((f for f in book.formats if f.chosen), None)


def propose_themes(session: Session, book: Book) -> list[ThemeOption]:
    avoid = [t.title for t in book.themes]
    out = structured("propose_themes", {"recipe": recipe_text(book.recipe), "avoid": ", ".join(avoid) or "none"},
                     ThemesOut)
    for t in list(book.themes):
        if not t.chosen:
            session.delete(t)
    session.flush()
    created = []
    for th in out.themes[:3]:
        opt = ThemeOption(book_id=book.id, title=th.title.strip(), description=th.description.strip())
        session.add(opt)
        created.append(opt)
    session.commit()
    session.refresh(book)
    return created


def choose_theme(session: Session, book: Book, theme_id: int, title: str | None = None) -> ThemeOption:
    target = None
    for t in book.themes:
        t.chosen = t.id == theme_id
        if t.chosen:
            target = t
    if target is None:
        raise KeyError(f"theme {theme_id} not found for this book")
    if title:
        target.title = title.strip()
    book.theme_id = target.id
    book.title = target.title
    if book.status in ("draft", "analyzed"):
        book.status = "themed"
    session.commit()
    return target


# ----------------------------------------------------------------- formats


def normalize_shares(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicate types, drop zeros, scale to integers summing to 100
    (largest remainder)."""
    merged: dict[str, float] = {}
    for b in blocks:
        t = b["type"]
        if t not in CONTENT_PAGE_TYPES:
            continue
        merged[t] = merged.get(t, 0) + max(0.0, float(b.get("share", 0)))
    merged = {k: v for k, v in merged.items() if v > 0}
    if not merged:
        return [{"type": "scene", "share": 100}]
    total = sum(merged.values())
    raw = {k: v * 100 / total for k, v in merged.items()}
    floors = {k: math.floor(v) for k, v in raw.items()}
    rest = 100 - sum(floors.values())
    for k in sorted(raw, key=lambda k: raw[k] - floors[k], reverse=True)[:rest]:
        floors[k] += 1
    return [{"type": k, "share": v} for k, v in sorted(floors.items(), key=lambda kv: -kv[1]) if v > 0]


def propose_formats(session: Session, book: Book, instruction: str | None = None) -> list[FormatOption]:
    theme = chosen_theme(book)
    instr = (f"The user asks for a NEW HYBRID format: \"{instruction.strip()}\". Return exactly 1 format."
             if instruction else "Return 3 or 4 clearly different formats.")
    out = structured("propose_formats",
                     {"recipe": recipe_text(book.recipe),
                      "theme": f"{theme.title}: {theme.description}" if theme else book.title,
                      "page_types": ", ".join(CONTENT_PAGE_TYPES), "instruction": instr,
                      **({"instruction_raw": instruction} if instruction else {})},
                     FormatsOut)
    if not instruction:
        for f in list(book.formats):
            if not f.chosen:
                session.delete(f)
        session.flush()
    created = []
    for f in out.formats[: (1 if instruction else 4)]:
        opt = FormatOption(book_id=book.id, name=f.name.strip(), description=f.description.strip(),
                           blocks=normalize_shares([b.model_dump() for b in f.blocks]))
        session.add(opt)
        created.append(opt)
    session.commit()
    session.refresh(book)
    return created


def choose_format(session: Session, book: Book, format_id: int, blocks: list[dict[str, Any]] | None = None) -> FormatOption:
    target = None
    for f in book.formats:
        f.chosen = f.id == format_id
        if f.chosen:
            target = f
    if target is None:
        raise KeyError(f"format {format_id} not found for this book")
    if blocks is not None:
        set_blocks(target, blocks)
    book.format_id = target.id
    session.commit()
    return target


def set_blocks(fmt: FormatOption, blocks: list[dict[str, Any]]) -> None:
    total = sum(int(b["share"]) for b in blocks)
    if total != 100:
        raise ValueError(f"shares must sum to 100 (got {total})")
    for b in blocks:
        if b["type"] not in CONTENT_PAGE_TYPES:
            raise ValueError(f"invalid page type in format: {b['type']}")
    fmt.blocks = [{"type": b["type"], "share": int(b["share"])} for b in blocks if int(b["share"]) > 0]


# -------------------------------------------------------------- page plan


def allocate_counts(blocks: list[dict[str, Any]], n: int) -> dict[str, int]:
    """Largest-remainder allocation of n pages by share; every type with a
    share > 0 gets at least one page when n allows."""
    blocks = [b for b in blocks if b["share"] > 0]
    if n <= 0 or not blocks:
        return {}
    total = sum(b["share"] for b in blocks)
    raw = {b["type"]: b["share"] * n / total for b in blocks}
    counts = {k: math.floor(v) for k, v in raw.items()}
    rest = n - sum(counts.values())
    for k in sorted(raw, key=lambda k: raw[k] - counts[k], reverse=True)[:rest]:
        counts[k] += 1
    if n >= len(blocks):
        for k in counts:
            if counts[k] == 0:
                donor = max(counts, key=lambda d: counts[d])
                counts[donor] -= 1
                counts[k] = 1
    return {k: v for k, v in counts.items() if v > 0}


def order_slots(counts: dict[str, int]) -> list[str]:
    """Spread each type evenly through the book (story pages keep order)."""
    items: list[tuple[float, int, str]] = []
    for ti, (t, c) in enumerate(sorted(counts.items(), key=lambda kv: -kv[1])):
        for i in range(c):
            items.append(((i + 0.5) / c, ti, t))
    items.sort()
    return [t for _, _, t in items]


def front_back_matter(book: Book) -> tuple[list[str], list[str]]:
    meta = book.meta or {}
    front = ["title_page"] + (["belongs_to_page"] if meta.get("belongs_to", True) else [])
    back = ["end_page"]
    return front, back


def content_slots(book: Book, fmt: FormatOption) -> list[str]:
    front, back = front_back_matter(book)
    n = max(1, book.page_count - len(front) - len(back))
    return order_slots(allocate_counts(fmt.blocks, n))


def _dedupe_descriptions(pages: list[dict[str, Any]]) -> None:
    seen: dict[str, int] = {}
    for p in pages:
        key = " ".join(p["description"].lower().split())
        if key in seen:
            seen[key] += 1
            p["description"] = f"{p['description']} (variation {seen[key]})"
        else:
            seen[key] = 1


def plan_pages(session: Session, book: Book) -> list[Page]:
    fmt = chosen_format(book)
    if fmt is None:
        raise ValueError("choose a format before planning pages")
    theme = chosen_theme(book)
    slots = content_slots(book, fmt)
    chars = [c for c in session.query(Character).filter(Character.book_id == book.id).all()]
    char_desc = "; ".join(f"{c.name} ({c.species}, {c.signature_feature})" for c in chars) or "none yet (describe generic friendly characters)"
    variables = {
        "theme": f"{theme.title}: {theme.description}" if theme else book.title,
        "recipe": recipe_text(book.recipe),
        "characters": char_desc,
        "book_language": book.book_language,
        "slots_json": json.dumps([{"n": i + 1, "type": t} for i, t in enumerate(slots)]),
        "page_count": len(slots),
        "slots": slots,
        "character_names": [c.name for c in chars],
    }
    out = structured("plan_pages", variables, PagePlanOut)
    planned = [p.model_dump() for p in out.pages]
    if len(planned) != len(slots):
        # one more try with an explicit correction, then pad/trim deterministically
        try:
            out = structured("plan_pages", {**variables, "theme": variables["theme"] + f" (IMPORTANT: exactly {len(slots)} pages)"},
                             PagePlanOut)
            planned = [p.model_dump() for p in out.pages]
        except LLMOutputError:
            pass
    planned = planned[: len(slots)]
    while len(planned) < len(slots):
        planned.append({"type": slots[len(planned)], "description": f"{variables['theme']} page {len(planned) + 1}",
                        "characters": [], "text_content": {}})
    for p, t in zip(planned, slots):
        p["type"] = t  # the order is fixed by code
    _dedupe_descriptions(planned)

    by_name = {c.name.lower(): c.id for c in chars}
    for old in list(book.pages):
        session.delete(old)
    session.flush()
    front, back = front_back_matter(book)
    rows: list[Page] = []
    idx = 1
    for t in front:
        rows.append(Page(book_id=book.id, index=idx, type=t, description=t.replace("_", " "), text_content={}))
        idx += 1
    for p in planned:
        rows.append(Page(book_id=book.id, index=idx, type=p["type"], description=p["description"].strip(),
                         text_content=p.get("text_content") or {},
                         meta={"characters": [by_name[n.lower()] for n in p.get("characters", []) if n.lower() in by_name],
                               "character_names": p.get("characters", [])}))
        idx += 1
    for t in back:
        rows.append(Page(book_id=book.id, index=idx, type=t, description=t.replace("_", " "), text_content={}))
        idx += 1
    session.add_all(rows)
    if book.status in ("draft", "analyzed", "themed"):
        book.status = "themed"
    book.meta = {**(book.meta or {}), "planned_slots": slots}
    session.commit()
    return rows


def page_summary(p: Page) -> dict[str, Any]:
    return {"id": p.id, "index": p.index, "type": p.type, "description": p.description, "status": p.status,
            "is_image": is_image_type(p.type), "text_content": p.text_content, "characters": (p.meta or {}).get("character_names", [])}
