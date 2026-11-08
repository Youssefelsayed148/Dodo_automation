"""Model -> JSON dicts for the API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..models import Book, Character, CharacterAsset, FormatOption, Job, Page, Recipe, ThemeOption
from ..schemas import is_image_type
from ..services.specs import SpecError, page_spec


def file_url(stored: str | None, thumb: bool = False) -> str | None:
    if not stored:
        return None
    return f"/api/files/{quote(stored)}" + ("?thumb=1" if thumb else "")


def recipe(r: Recipe | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {"mood": r.mood, "age_group": r.age_group, "line_weight": r.line_weight, "detail_level": r.detail_level,
            "page_mix": r.page_mix or [], "confidence": r.confidence, "notes": r.notes}


def theme(t: ThemeOption) -> dict[str, Any]:
    return {"id": t.id, "title": t.title, "description": t.description, "chosen": t.chosen}


def fmt(f: FormatOption) -> dict[str, Any]:
    return {"id": f.id, "name": f.name, "description": f.description, "blocks": f.blocks or [], "chosen": f.chosen}


def page(p: Page) -> dict[str, Any]:
    meta = p.meta or {}
    return {"id": p.id, "index": p.index, "type": p.type, "is_image": is_image_type(p.type),
            "description": p.description, "prompt": p.prompt, "text_content": p.text_content or {},
            "status": p.status, "attempts": p.attempts, "batch_no": p.batch_no, "qa": p.qa or {},
            "image_url": file_url(p.image_path), "thumb_url": file_url(p.image_path, thumb=True),
            "characters": meta.get("character_names", []), "note": meta.get("note")}


def book(b: Book, full: bool = False) -> dict[str, Any]:
    try:
        spec = page_spec(b.trim_size, b.bleed).as_dict()
    except SpecError:
        spec = None
    meta = b.meta or {}
    counts: dict[str, int] = {}
    for p in b.pages:
        counts[p.status] = counts.get(p.status, 0) + 1
    out = {"id": b.id, "title": b.title, "status": b.status, "source_type": b.source_type, "source_url": b.source_url,
           "source_text": b.source_text, "book_language": b.book_language, "trim_size": b.trim_size, "bleed": b.bleed,
           "page_count": b.page_count, "theme_id": b.theme_id, "format_id": b.format_id,
           "created_at": b.created_at.isoformat() if b.created_at else None, "spec": spec,
           "page_status_counts": counts, "thumb_url": None,
           "fetch": {k: v for k, v in (meta.get("fetch") or {}).items() if k != "brand_terms"},
           "sample": {**(meta.get("sample") or {}), "url": file_url((meta.get("sample") or {}).get("path"))},
           "cover": {**(meta.get("cover") or {}), "art_url": file_url((meta.get("cover") or {}).get("art_path"))},
           "belongs_to": meta.get("belongs_to", True), "image_provider": meta.get("image_provider") or "",
           "drive": meta.get("drive") or {}, "content_check": meta.get("content_check"),
           "prompt_batches_done": meta.get("prompt_batches_done") or [],
           "style_anchor": {"rules": (b.style_anchor or {}).get("rules"),
                            "reference_url": file_url((b.style_anchor or {}).get("reference_path"))}}
    first = next((p for p in sorted(b.pages, key=lambda p: p.index) if p.image_path and is_image_type(p.type)), None)
    if first:
        out["thumb_url"] = file_url(first.image_path, thumb=True)
    if full:
        out["recipe"] = recipe(b.recipe)
        out["themes"] = [theme(t) for t in b.themes]
        out["formats"] = [fmt(f) for f in b.formats]
    return out


def asset(a: CharacterAsset) -> dict[str, Any]:
    return {"id": a.id, "kind": a.kind, "selected": a.selected, "meta": a.meta or {},
            "url": file_url(a.path), "thumb_url": file_url(a.path, thumb=True)}


def character(c: Character) -> dict[str, Any]:
    brief = c.brief or {}
    return {"id": c.id, "book_id": c.book_id, "name": c.name, "species": c.species, "personality": c.personality,
            "signature_feature": c.signature_feature, "proportions": c.proportions, "outfit": brief.get("outfit", ""),
            "status": c.status, "in_library": c.in_library, "versions": brief.get("versions", []),
            "consistency": brief.get("consistency"), "assets": [asset(a) for a in c.assets]}


def job(j: Job) -> dict[str, Any]:
    return {"id": j.id, "book_id": j.book_id, "type": j.type, "status": j.status, "progress": j.progress,
            "message": j.message, "result": j.result or {}, "error": j.error, "payload": j.payload or {},
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None}
