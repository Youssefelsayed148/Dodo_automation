"""Registered job handlers. Each is idempotent / resumable where it matters."""

from __future__ import annotations

from typing import Any

from ..models import Book, Character
from ..providers.base import usage_context
from .runner import JobContext, handler


def _book(s, ctx: JobContext) -> Book:
    book = s.get(Book, ctx.book_id or ctx.payload.get("book_id"))
    if book is None:
        raise ValueError("book not found")
    return book


def _char(s, ctx: JobContext) -> Character:
    c = s.get(Character, ctx.payload["character_id"])
    if c is None:
        raise ValueError("character not found")
    return c


@handler("noop")
def noop(ctx: JobContext) -> dict[str, Any]:
    """Test job: reports progress in steps; fails if payload.fail."""
    steps = int(ctx.payload.get("steps", 3))
    for i in range(steps):
        ctx.check_cancel()
        ctx.progress((i + 1) / steps, f"step {i + 1}/{steps}")
    if ctx.payload.get("fail"):
        raise RuntimeError("requested failure")
    return {"steps": steps}


@handler("analyze_source")
def analyze_source(ctx: JobContext) -> dict[str, Any]:
    from ..services.analysis import analyze_book

    with ctx.session() as s:
        book = _book(s, ctx)
        with usage_context(book_id=book.id, purpose="analysis"):
            recipe = analyze_book(s, book, ctx.progress)
        fetch = (book.meta or {}).get("fetch") or {}
        return {"recipe_id": recipe.id, "fetch_status": fetch.get("status", "none"), "confidence": recipe.confidence}


@handler("propose_themes")
def propose_themes(ctx: JobContext) -> dict[str, Any]:
    from ..services.planning import propose_themes as run

    with ctx.session() as s:
        book = _book(s, ctx)
        with usage_context(book_id=book.id, purpose="planning"):
            return {"themes": [t.id for t in run(s, book)]}


@handler("propose_formats")
def propose_formats(ctx: JobContext) -> dict[str, Any]:
    from ..services.planning import propose_formats as run

    with ctx.session() as s:
        book = _book(s, ctx)
        with usage_context(book_id=book.id, purpose="planning"):
            return {"formats": [f.id for f in run(s, book, ctx.payload.get("instruction"))]}


@handler("plan_pages")
def plan_pages(ctx: JobContext) -> dict[str, Any]:
    from ..services.planning import plan_pages as run

    with ctx.session() as s:
        book = _book(s, ctx)
        with usage_context(book_id=book.id, purpose="planning"):
            return {"pages": len(run(s, book))}


@handler("character_briefs")
def character_briefs(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import generate_briefs

    with ctx.session() as s:
        book = _book(s, ctx)
        with usage_context(book_id=book.id, purpose="character"):
            return {"characters": [c.id for c in generate_briefs(s, book, int(ctx.payload.get("count", 1)))]}


@handler("character_candidates")
def character_candidates(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import generate_candidates

    with ctx.session() as s:
        book, c = _book(s, ctx), _char(s, ctx)
        return {"assets": [a.id for a in generate_candidates(s, book, c, progress=ctx.progress)]}


@handler("character_edit")
def character_edit(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import edit_character

    with ctx.session() as s:
        book, c = _book(s, ctx), _char(s, ctx)
        with usage_context(book_id=book.id, purpose="character"):
            return {"asset": edit_character(s, book, c, ctx.payload["instruction"]).id}


@handler("character_sheet")
def character_sheet(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import generate_sheet

    with ctx.session() as s:
        book, c = _book(s, ctx), _char(s, ctx)
        return {"assets": [a.id for a in generate_sheet(s, book, c, progress=ctx.progress)]}


@handler("character_consistency")
def character_consistency(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import run_consistency_test

    with ctx.session() as s:
        book, c = _book(s, ctx), _char(s, ctx)
        return run_consistency_test(s, book, c, progress=ctx.progress)


@handler("sample_page")
def sample_page(ctx: JobContext) -> dict[str, Any]:
    from ..services.characters import generate_sample

    with ctx.session() as s:
        return generate_sample(s, _book(s, ctx))


@handler("generate_pages")
def generate_pages(ctx: JobContext) -> dict[str, Any]:
    from ..services.generation import run_generation

    return run_generation(ctx.book_id, ctx)


@handler("cover_art")
def cover_art(ctx: JobContext) -> dict[str, Any]:
    from ..services import storage
    from ..services.characters import provider_name, sheet_ref_paths, style_anchor, style_ref_paths
    from ..services.cleanup import clean_line_art, save_print_png
    from ..services.generation import image_size_hint
    from ..services.manual import ImageReq, image_batch
    from ..services.specs import page_spec

    with ctx.session() as s:
        book = _book(s, ctx)
        chars = s.query(Character).filter(Character.book_id == book.id).all()
        rules, _ = style_anchor(book)
        who = " and ".join(c.name for c in chars) or "the main characters"
        prompt = (f"Cover illustration for a children's coloring book about {book.title}: {who} posing happily, "
                  f"leave the top quarter of the image empty for a title. {rules}")
        refs = (style_ref_paths(book) + [p for c in chars for p in sheet_ref_paths(c, 1)])[:4]
        with usage_context(book_id=book.id, purpose="cover"):
            [data] = image_batch(book.id, "cover", [ImageReq(prompt, label="cover", refs=refs, size=image_size_hint(book))],
                                 group="cover", provider_name=provider_name(book))
        if data is None:  # skipped in ChatGPT: a page can be used as cover art instead
            return {"skipped": True}
        path = storage.sub(book.id, "cover") / "cover_art.png"
        save_print_png(clean_line_art(data, page_spec(book.trim_size, book.bleed)), path)
        meta = dict(book.meta or {})
        meta["cover"] = {**(meta.get("cover") or {}), "art_path": storage.rel(path)}
        book.meta = meta
        s.commit()
        return {"art_path": storage.rel(path)}


@handler("export_book")
def export_book(ctx: JobContext) -> dict[str, Any]:
    from ..services import drive, storage
    from ..services.export import write_local_export

    with ctx.session() as s:
        book = _book(s, ctx)
        res = write_local_export(s, book, lambda p, m=None: ctx.progress(p * 0.6, m),
                                 include_unapproved=bool(ctx.payload.get("include_unapproved")))
        out: dict[str, Any] = {"local": res}
        if ctx.payload.get("drive"):
            ctx.progress(0.6, "uploading to Google Drive")
            client = drive.GoogleDriveClient()
            meta = dict(book.meta or {})
            prev = meta.get("drive") or {}
            folder_name = ctx.payload.get("folder_name") or book.title
            resume = prev.get("folder_id") if prev.get("partial") and prev.get("folder_name") == drive.sanitize_folder_name(folder_name) else None
            meta["drive"] = {"partial": True, "folder_name": drive.sanitize_folder_name(folder_name), **({"folder_id": resume} if resume else {})}
            book.meta = meta
            s.commit()
            up = drive.upload_export(client, folder_name, storage.export_dir(book.id), resume_folder_id=resume,
                                     progress=lambda p, m=None: ctx.progress(0.6 + 0.4 * p, m))
            meta = dict(book.meta or {})
            meta["drive"] = {**up, "partial": False}
            book.meta = meta
            s.commit()
            out["drive"] = up
        return out


@handler("compare_providers")
def compare_providers(ctx: JobContext) -> dict[str, Any]:
    from ..services import storage
    from ..services.compare import DEFAULT_THEME, run_compare

    sheet = storage.read_bytes(ctx.payload.get("sheet_path")) if ctx.payload.get("sheet_path") else None
    res = run_compare(ctx.payload.get("providers") or ["mock"], ctx.payload.get("theme") or DEFAULT_THEME,
                      sheet, ctx.payload.get("scenes"), progress=ctx.progress)
    return {"run": res["run"], "summary": res["summary"]}
