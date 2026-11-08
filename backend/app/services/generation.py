"""Page generation, QA and auto-redo (PLAN.md section 12).

Image pages: prompt (style anchor + characters + scene) -> image provider ->
programmatic QA -> vision QA -> cleanup -> PNG. Failed QA appends the issues
to the prompt and retries up to `max_redo` times, then marks the page failed.
Code pages are rendered without the image model.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Book, Character, Page
from ..providers.base import usage_context
from ..providers.registry import get_image_provider
from ..schemas import ImagePromptOut, QAContentOut, VisionVerdict, is_image_type
from . import qa_checks, settings_service, storage
from .characters import describe, sheet_images, style_anchor
from .cleanup import clean_line_art, make_thumbnail, save_print_png
from .llm import structured
from .specs import page_spec

log = logging.getLogger(__name__)

PAGE_TYPE_HINTS = {
    "single_character": "one character, large, centered, simple or no background",
    "scene": "full scene with characters and a simple setting",
    "pattern_mandala": "symmetrical decorative pattern/mandala with the theme's motifs, no characters needed",
    "hidden_objects_scene": "busy but clear scene with 6-10 small objects hidden in it",
}


class CostCeilingReached(RuntimeError):
    pass


def image_size_hint(book: Book) -> tuple[int, int]:
    w, h = page_spec(book.trim_size, book.bleed).pixel_size
    return w, h


def build_image_prompt(book: Book, page_type: str, description: str, chars: list[Character], issues: list[str],
                       note: str | None = None) -> str:
    rules, _ = style_anchor(book)
    char_text = "\n".join(f"- {describe(c)}" for c in chars) or "- none"
    out = structured("page_image_prompt",
                     {"style_rules": rules, "characters": char_text,
                      "description": f"{description}. ({PAGE_TYPE_HINTS.get(page_type, '')})" + (f" User note: {note}" if note else ""),
                      "page_type": page_type, "issues": "; ".join(issues) or "none"},
                     ImagePromptOut)
    prompt = out.prompt.strip()
    # The essentials are always appended by code, whatever the model wrote.
    prompt += f"\n\nStyle: {rules}"
    if issues:
        prompt += "\nAvoid these problems from the previous attempt: " + "; ".join(issues)
    return prompt


def page_characters(session: Session, page: Page) -> list[Character]:
    ids = (page.meta or {}).get("characters") or []
    if not ids:
        return []
    return list(session.scalars(select(Character).where(Character.id.in_(ids))).all())


def _save_outputs(book: Book, page: Page, img) -> str:
    path = storage.pages_dir(book.id) / f"page_{page.index:03d}.png"
    save_print_png(img, path)
    stored = storage.rel(path)
    make_thumbnail(path, storage.thumb_for(stored))
    return stored


def generate_image_page(session: Session, book: Book, page: Page, *, max_redo: int, vision_qa: bool = True) -> str:
    chars = page_characters(session, page)
    _, style_refs = style_anchor(book)
    refs = (style_refs + [img for c in chars for img in sheet_images(c, 1)])[:4]
    provider = get_image_provider((book.meta or {}).get("image_provider") or None)
    spec = page_spec(book.trim_size, book.bleed)
    meta = dict(page.meta or {})
    note = meta.get("note")
    issues: list[str] = list(meta.get("redo_issues") or [])
    history: list[dict[str, Any]] = []
    last_image = None
    for _attempt in range(max_redo + 1):
        prompt = build_image_prompt(book, page.type, page.description, chars, issues, note)
        with usage_context(book_id=book.id, page_id=page.id, purpose="page"):
            raw = provider.generate(prompt, image_size_hint(book), reference_images=refs, seed=page.index * 100 + page.attempts)
        page.attempts = (page.attempts or 0) + 1
        page.prompt = prompt
        last_image = raw
        prog = qa_checks.analyze(raw)
        verdict: dict[str, Any] = {"pass": True, "issues": []}
        if prog["pass"] and vision_qa:
            sheet = [img for c in chars for img in sheet_images(c, 1)][:3]
            with usage_context(book_id=book.id, page_id=page.id, purpose="qa"):
                v = structured("qa_vision_check",
                               {"page_type": page.type, "description": page.description,
                                "characters": "; ".join(f"{c.name} ({c.signature_feature})" for c in chars) or "none"},
                               VisionVerdict, images=[raw] + sheet)
            verdict = v.as_dict()
        attempt_issues = prog["issues"] + (verdict.get("issues") or [] if not verdict.get("pass") else [])
        history.append({"attempt": page.attempts, "programmatic": prog, "vision": verdict})
        if prog["pass"] and verdict.get("pass"):
            img = clean_line_art(raw, spec)
            page.image_path = _save_outputs(book, page, img)
            page.qa = {"pass": True, "history": history, "metrics": prog["metrics"], "warnings": prog["warnings"]}
            page.status = "generated"
            meta.pop("redo_issues", None)
            page.meta = meta
            session.commit()
            return "generated"
        issues = list(dict.fromkeys(issues + attempt_issues))
        session.commit()
    # out of attempts: keep the last image for review, mark failed
    if last_image is not None:
        try:
            page.image_path = _save_outputs(book, page, clean_line_art(last_image, spec))
        except Exception:  # noqa: BLE001
            log.exception("could not save failed image for page %s", page.id)
    page.qa = {"pass": False, "history": history, "issues": issues}
    page.status = "failed"
    session.commit()
    return "failed"


def generate_code_page(session: Session, book: Book, page: Page) -> str:
    from ..render import render_code_page

    spec = page_spec(book.trim_size, book.bleed)
    path = storage.pages_dir(book.id) / f"page_{page.index:03d}.png"
    render_code_page(page.type, page.text_content or {}, spec, book.book_language, path,
                     book_title=book.title, seed_key=f"{book.id}-{page.id}")
    stored = storage.rel(path)
    make_thumbnail(path, storage.thumb_for(stored))
    page.image_path = stored
    page.attempts = (page.attempts or 0) + 1
    page.qa = {"pass": True, "code_rendered": True}
    page.status = "generated"
    session.commit()
    return "generated"


def generate_one(page_id: int, max_redo: int, vision_qa: bool) -> str:
    with SessionLocal() as s:
        page = s.get(Page, page_id)
        if page is None:
            return "missing"
        book = s.get(Book, page.book_id)
        try:
            if is_image_type(page.type):
                return generate_image_page(s, book, page, max_redo=max_redo, vision_qa=vision_qa)
            return generate_code_page(s, book, page)
        except Exception as e:  # noqa: BLE001 - one page failing must not stop the book
            log.exception("page %s failed", page_id)
            s.rollback()
            page = s.get(Page, page_id)
            page.status = "failed"
            page.qa = {**(page.qa or {}), "pass": False, "error": f"{type(e).__name__}: {e}"}
            s.commit()
            return "failed"


def check_content(session: Session, book: Book) -> dict[str, Any]:
    pages = [p for p in book.pages if p.type in ("story_text", "qa_page", "word_search", "trace_write")]
    if not pages:
        return {"ok": True, "issues": []}
    payload = [{"page": p.index, "type": p.type, "text_content": p.text_content} for p in pages]
    with usage_context(book_id=book.id, purpose="qa"):
        out = structured("qa_content", {"book_language": book.book_language, "pages_json": json.dumps(payload, ensure_ascii=False)},
                         QAContentOut)
    return out.model_dump()


def queue_pages(session: Session, book: Book, page_ids: list[int] | None = None, note: str | None = None,
                only_rejected: bool = False) -> list[int]:
    ids = []
    for p in book.pages:
        if page_ids is not None and p.id not in page_ids:
            continue
        if only_rejected and p.status != "rejected":
            continue
        if page_ids is None and not only_rejected and p.status not in ("planned", "failed", "queued"):
            continue
        meta = dict(p.meta or {})
        if note:
            meta["note"] = note
        if p.status == "rejected" and p.qa:
            meta["redo_issues"] = ["user rejected the previous version"] + ([note] if note else [])
        p.meta = meta
        p.status = "queued"
        ids.append(p.id)
    session.commit()
    return ids


def ensure_ready(session: Session, book: Book) -> None:
    from .characters import GateError, gates_status

    if not book.pages:
        raise GateError("plan the pages first")
    if any(is_image_type(p.type) for p in book.pages):
        g = gates_status(session, book)
        if not g["characters_ok"]:
            raise GateError("all characters must be approved before generating")
        if not g["sample_ok"]:
            raise GateError("approve the sample page before generating")


def run_generation(book_id: int, ctx) -> dict[str, Any]:
    """Job body: process queued pages of a book in batches. Resumable: only
    `queued` pages are processed, so a restart continues where it stopped."""
    from ..jobs.runner import JobStopped
    from .usage import book_cost

    with SessionLocal() as s:
        book = s.get(Book, book_id)
        settings = settings_service.get_all(s)
        batch_size = int(settings["batch_size"])
        concurrency = int(settings["concurrency"])
        max_redo = int(settings["max_redo"])
        vision_qa = bool(settings["vision_qa"])
        ceiling = float(settings["cost_ceiling_usd"] or 0)
        page_ids = ctx.payload.get("page_ids")
        q = select(Page).where(Page.book_id == book_id, Page.status == "queued").order_by(Page.index)
        pages = [p for p in s.scalars(q).all() if not page_ids or p.id in page_ids]
        todo = [p.id for p in pages]
        book.status = "generating"
        if not (book.meta or {}).get("content_check") and any(p.type in ("story_text", "qa_page", "word_search") for p in book.pages):
            try:
                book.meta = {**(book.meta or {}), "content_check": check_content(s, book)}
            except Exception as e:  # noqa: BLE001
                log.warning("content QA skipped: %s", e)
        s.commit()
    total = len(todo)
    done = 0
    counts = {"generated": 0, "failed": 0}
    batches = [todo[i:i + batch_size] for i in range(0, total, batch_size)]
    for bno, batch in enumerate(batches, start=1):
        ctx.check_cancel()
        if ceiling > 0:
            with SessionLocal() as s:
                spent = book_cost(s, book_id)
            if spent >= ceiling:
                raise JobStopped(f"cost ceiling reached (${spent:.2f} of ${ceiling:.2f}); raise it in Settings and resume")
        with SessionLocal() as s:
            for pid in batch:
                p = s.get(Page, pid)
                if p is not None:
                    p.batch_no = bno
            s.commit()
        ctx.progress(done / max(total, 1), f"batch {bno}/{len(batches)}", batch=bno, batches=len(batches), **counts)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for status in pool.map(lambda pid: generate_one(pid, max_redo, vision_qa), batch):
                done += 1
                if status in counts:
                    counts[status] += 1
                ctx.progress(done / max(total, 1), f"batch {bno}/{len(batches)}: {done}/{total} pages",
                             batch=bno, batches=len(batches), **counts)
    with SessionLocal() as s:
        book = s.get(Book, book_id)
        remaining = s.scalar(select(Page.id).where(Page.book_id == book_id, Page.status.in_(("queued", "planned"))).limit(1))
        if remaining is None:
            book.status = "review"
        s.commit()
        redo_total = sum(max(0, (p.attempts or 0) - 1) for p in book.pages)
    return {**counts, "total": total, "redos": redo_total}
