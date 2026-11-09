"""Manual mode: "Set up ChatGPT for this book" - project instructions built
from the Book Brief plus the reference images to upload to the project."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..models import Book, Character
from .characters import selected_asset, style_ref_paths
from .export_prompts import brief_text, build_brief

WORKFLOW_RULES = [
    "HOW WE WORK IN THIS PROJECT:",
    "- I send one task per message. Follow it exactly.",
    "- Text tasks: reply with ONE JSON object only, exactly in the requested format, with no explanations.",
    "- Image tasks: create exactly ONE image per request. Black-and-white coloring-book line art, portrait (tall) "
    "unless the task says otherwise, pure white background, clean closed bold black outlines, no grey, no shading, "
    "no filled black areas, a white margin around the drawing, and NO text, letters or numbers inside the image.",
    "- The reference images in this project show the line style and the characters. Keep every character identical "
    "to its reference sheet on every page (face, proportions, signature feature, outfit).",
]


def chatgpt_setup(session: Session, book: Book) -> dict[str, Any]:
    brief = build_brief(session, book)
    instructions = "\n".join(
        ["You help me make an original children's coloring / activity book. These are the project instructions for "
         "every chat in this project.", "", brief_text(brief), ""] + WORKFLOW_RULES)
    refs: list[dict[str, Any]] = [{"kind": "style", "name": "", "path": p} for p in style_ref_paths(book)]
    seen = {r["path"] for r in refs}
    chars = session.query(Character).filter(Character.book_id == book.id).order_by(Character.id).all()
    for c in chars:
        sheet = next((a for a in c.assets if a.kind == "sheet" and (a.meta or {}).get("view") in ("combined", "front")), None)
        sel = selected_asset(c)
        for kind, a in (("sheet", sheet), ("character", sel)):
            if a is not None and a.path not in seen:
                refs.append({"kind": kind, "name": c.name, "path": a.path})
                seen.add(a.path)
    return {"instructions": instructions, "references": refs, "project_name": book.title}
