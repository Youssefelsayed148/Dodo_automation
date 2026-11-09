"""Manual mode (ChatGPT tasks) API: list tasks, answer them, skip, setup card."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..jobs.runner import ACTIVE_STATUSES
from ..models import Book, Job, ManualTask
from ..services import manual, storage
from ..services.uploads import sniff
from . import serialize as ser
from .deps import get_book

router = APIRouter(prefix="/api", tags=["manual"])
MAX_BULK_FILES = 40
MEDIA = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "pdf": "application/pdf"}


class TextIn(BaseModel):
    text: str


def task_out(t: ManualTask, jobs: dict[int, Job] | None = None) -> dict:
    meta = t.meta or {}
    job = (jobs or {}).get(t.job_id) if t.job_id else None
    refs = [{"index": i, "url": f"/api/manual/{t.id}/ref/{i}", "name": f"reference_{t.id}_{i + 1}"}
            for i, _ in enumerate(meta.get("refs") or [])]
    return {
        "id": t.id, "job_id": t.job_id, "job_type": job.type if job else None, "kind": t.kind, "task": t.task,
        "group": t.group, "title": t.title, "prompt": t.prompt, "status": t.status, "label": str(meta.get("label", "")),
        "refs": refs, "size": meta.get("size"), "skippable": t.kind == "image" and bool(meta.get("skippable", True)),
        "expected_count": meta.get("expected_count"), "character": meta.get("character"),
        "page_index": meta.get("page_index"), "scene": meta.get("scene"),
        "answer_url": ser.file_url(t.answer_path) if t.answer_path else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "answered_at": t.answered_at.isoformat() if t.answered_at else None,
    }


def _get_task(db: Session, task_id: int) -> ManualTask:
    t = db.get(ManualTask, task_id)
    if t is None:
        raise HTTPException(404, "task not found")
    return t


@router.get("/books/{book_id}/manual")
def list_tasks(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    jobs = {j.id: j for j in db.scalars(select(Job).where(Job.book_id == book.id, Job.status.in_(ACTIVE_STATUSES))).all()}
    return {
        "manual_mode": manual.is_manual(db),
        "chatgpt_url": manual.CHATGPT_URL,
        "pending": [task_out(t, jobs) for t in manual.open_tasks(db, book.id)],
        "recent": [task_out(t, jobs) for t in manual.recent_tasks(db, book.id)],
        "active_jobs": [ser.job(j) for j in jobs.values()],
    }


@router.post("/manual/{task_id}/text")
def answer_text(task_id: int, body: TextIn, db: Session = Depends(get_db)):
    _get_task(db, task_id)
    try:
        t = manual.submit_text(db, task_id, body.text)
    except manual.SubmitError as e:
        raise HTTPException(422, {"errors": e.errors, "fix_prompt": e.fix_prompt})
    except manual.TaskStateError as e:
        raise HTTPException(409, str(e))
    return task_out(t)


@router.post("/manual/{task_id}/image")
async def answer_image(task_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    _get_task(db, task_id)
    data = await file.read()
    try:
        t = manual.submit_image(db, task_id, data)
    except manual.TaskStateError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, f"{file.filename or 'image'}: {e}")
    return task_out(t)


@router.post("/books/{book_id}/manual/images")
async def answer_images_bulk(files: list[UploadFile] = File(...), book: Book = Depends(get_book), db: Session = Depends(get_db)):
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(422, f"at most {MAX_BULK_FILES} files at once")
    items = [(f.filename or f"file_{i + 1}", await f.read()) for i, f in enumerate(files)]
    return manual.bulk_images(db, book.id, [(n, d) for n, d in items if d])


@router.post("/manual/{task_id}/skip")
def skip_task(task_id: int, db: Session = Depends(get_db)):
    _get_task(db, task_id)
    try:
        return task_out(manual.skip(db, task_id))
    except manual.TaskStateError as e:
        raise HTTPException(409, str(e))


@router.get("/manual/{task_id}/ref/{n}")
def task_ref(task_id: int, n: int, db: Session = Depends(get_db)):
    t = _get_task(db, task_id)
    refs = (t.meta or {}).get("refs") or []
    if not 0 <= n < len(refs):
        raise HTTPException(404, "reference not found")
    root = get_settings().data_dir.resolve()
    p = storage.abs_path(refs[n])
    if p is None or not p.is_file() or root not in p.resolve().parents:
        raise HTTPException(404, "reference file is gone")
    kind = sniff(p.read_bytes()[:16])
    if kind not in MEDIA:
        raise HTTPException(404, "reference is not an image")
    return FileResponse(p, media_type=MEDIA[kind], filename=f"reference_{task_id}_{n + 1}.{kind}",
                        content_disposition_type="inline", headers={"Cache-Control": "no-cache"})


@router.get("/books/{book_id}/chatgpt-setup")
def chatgpt_setup(book: Book = Depends(get_book), db: Session = Depends(get_db)):
    return manual_setup(db, book)


def manual_setup(db: Session, book: Book) -> dict:
    from ..services.manual_setup import chatgpt_setup as build

    out = build(db, book)
    out["references"] = [{"kind": r["kind"], "name": r["name"], "url": ser.file_url(r["path"])} for r in out["references"]]
    return out
