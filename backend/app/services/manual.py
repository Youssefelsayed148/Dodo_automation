"""Manual mode: every AI step becomes a "ChatGPT task" (MANUAL_MODE_PLAN.md).

The user runs the prompt in ChatGPT and hands back JSON (text tasks) or an
image (image tasks). Mechanics:

- A handler asks for an answer (`request_text`, `image_batch`). If it is
  stored, it is returned; otherwise the task(s) are created and
  `AwaitingManual` is raised, which parks the job as `waiting`.
- Answers are found again by a deterministic `key` (hash of kind, task,
  prompt, seed and - unless `stable` - the job id), so a re-run job never
  asks twice. All image requests of a step are made before any side effects.
- `submit_text` validates JSON against the Pydantic model named in the task
  and returns readable errors plus a ready-made fix prompt; `submit_image`,
  `bulk_images` and `skip` store answers. When the last pending task of a job
  is answered the job is queued again and resumes by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..jobs.runner import ACTIVE_STATUSES, AwaitingManual, current_job, resume_if_ready
from ..models import Job, ManualTask, Setting, utcnow
from ..providers.jsonutil import JSONExtractError, extract_json
from . import storage

MAX_ANSWER_IMAGE_BYTES = 30 * 1024 * 1024
CHATGPT_URL = "https://chatgpt.com/"


class ManualModeError(RuntimeError):
    pass


class TaskStateError(ValueError):
    """The task cannot take this action (already answered, not skippable...)."""


class SubmitError(ValueError):
    """Invalid answer: readable errors and a prompt to paste back into ChatGPT."""

    def __init__(self, errors: list[str], fix_prompt: str):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.fix_prompt = fix_prompt


# ------------------------------------------------------------------ switch


def env_manual() -> bool | None:
    v = os.environ.get("MANUAL_MODE", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return None


def auto_manual() -> bool:
    """Auto: manual when there is no paid text model and no real image provider."""
    s = get_settings()
    return not s.anthropic_api_key and s.image_provider in ("mock", "manual")


def setting_manual(session: Session | None = None) -> bool | None:
    try:
        if session is not None:
            row = session.get(Setting, "manual_mode")
            return None if row is None or row.value is None else bool(row.value)
        with SessionLocal() as s:
            row = s.get(Setting, "manual_mode")
            return None if row is None or row.value is None else bool(row.value)
    except Exception:  # noqa: BLE001 - no DB yet (pure unit tests): fall back to env
        return None


def is_manual(session: Session | None = None) -> bool:
    """Setting (DB) first, then MANUAL_MODE env, then auto."""
    v = setting_manual(session)
    if v is None:
        v = env_manual()
    if v is None:
        v = auto_manual()
    return v


def mode_info(session: Session | None = None) -> dict[str, Any]:
    return {"active": is_manual(session), "setting": setting_manual(session), "env": env_manual(), "auto": auto_manual()}


# ----------------------------------------------------------------- helpers


def task_key(*parts: Any) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:40]


def _ctx() -> tuple[int, int]:
    cur = current_job.get()
    if cur is None or cur[1] is None:
        raise ManualModeError("ChatGPT tasks can only be created by a job that belongs to a book")
    return cur[0], int(cur[1])


def _jsonable(v: Any) -> Any:
    return json.loads(json.dumps(v, default=str, ensure_ascii=False))


def _strip_titles(node: Any, in_props: bool = False) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "title" and not in_props and isinstance(v, str):
                continue
            out[k] = _strip_titles(v, in_props=(not in_props and k in ("properties", "$defs")))
        return out
    if isinstance(node, list):
        return [_strip_titles(x) for x in node]
    return node


def compact_schema(schema: dict[str, Any]) -> str:
    return json.dumps(_strip_titles(schema), separators=(",", ":"), ensure_ascii=False)


JSON_REPLY_RULE = "Reply with ONE JSON object only (no explanations, nothing before or after it). It must match this JSON schema:"


def text_prompt(prompt: str, schema: dict[str, Any] | None, refs_count: int = 0) -> str:
    out = prompt.rstrip()
    if refs_count:
        out += (f"\n\nI attached {refs_count} picture(s) of the liked book to this message. Use them only to read the "
                "abstract style formula.")
    if schema:
        out += f"\n\n---\n{JSON_REPLY_RULE}\n{compact_schema(schema)}"
    return out


def schema_model(name: str | None) -> type[BaseModel] | None:
    if not name:
        return None
    from .. import schemas

    obj = getattr(schemas, name, None)
    return obj if isinstance(obj, type) and issubclass(obj, BaseModel) else None


# -------------------------------------------------------------- text tasks


def request_text(task: str, prompt: str, *, model_name: str | None = None, meta: dict[str, Any] | None = None) -> str:
    """Return the user's stored answer for this prompt, or create the task and
    raise AwaitingManual."""
    job_id, book_id = _ctx()
    key = task_key("text", job_id, task, prompt)
    meta = dict(meta or {})
    with SessionLocal() as s:
        t = s.scalar(select(ManualTask).where(ManualTask.book_id == book_id, ManualTask.key == key))
        if t is not None:
            if t.status == "done":
                return t.answer_text or ""
            if t.status == "skipped":
                raise ManualModeError(f"ChatGPT task '{task}' was skipped")
            raise AwaitingManual([t.id])
        m = {"model": model_name, "skippable": False}
        for k in ("vars", "refs", "expected_count", "count_field", "title_vars"):
            if k in meta and meta[k] is not None:
                m[k] = _jsonable(meta[k])
        t = ManualTask(book_id=book_id, job_id=job_id, kind="text", task=task, key=key, group=task,
                       title=task.replace("_", " "), prompt=prompt, meta=m, status="pending")
        s.add(t)
        s.commit()
        raise AwaitingManual([t.id])


def _err_line(err: dict[str, Any]) -> str:
    loc = " → ".join(str(x) for x in err.get("loc", ()) if x != "__root__")
    return f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid"))


def fix_prompt(task: ManualTask, errors: list[str]) -> str:
    meta = task.meta or {}
    lines = ["Your last answer could not be used:"] + [f"- {e}" for e in errors] + [""]
    lines.append("Please answer the same request again.")
    if meta.get("expected_count") and meta.get("count_field"):
        lines.append(f'The list "{meta["count_field"]}" must contain exactly {meta["expected_count"]} items.')
    model = schema_model(meta.get("model"))
    if model is not None:
        lines += [JSON_REPLY_RULE, compact_schema(model.model_json_schema())]
    else:
        lines.append("Reply with ONE corrected JSON object only.")
    return "\n".join(lines)


def validate_text(task: ManualTask, text: str) -> Any:
    meta = task.meta or {}
    errors: list[str] = []
    data: Any = None
    if not (text or "").strip():
        errors.append("The answer is empty. Paste ChatGPT's whole reply (or just its JSON block).")
    else:
        try:
            data = extract_json(text)
        except JSONExtractError:
            errors.append("No valid JSON object was found. Paste ChatGPT's whole reply (or just its JSON block).")
    model = schema_model(meta.get("model"))
    if not errors and model is not None:
        try:
            model.model_validate(data)
        except ValidationError as e:
            errors += [_err_line(err) for err in e.errors()[:12]]
    exp, fld = meta.get("expected_count"), meta.get("count_field")
    if not errors and exp and fld:
        n = len(data.get(fld) or []) if isinstance(data, dict) and isinstance(data.get(fld), list) else 0
        if n != int(exp):
            errors.append(f'"{fld}" must contain exactly {exp} items (got {n}).')
    if errors:
        raise SubmitError(errors, fix_prompt(task, errors))
    return data


def _get_task(session: Session, task_id: int) -> ManualTask:
    t = session.get(ManualTask, task_id)
    if t is None:
        raise KeyError(f"task {task_id} not found")
    return t


def _job_waiting(session: Session, t: ManualTask) -> bool:
    job = session.get(Job, t.job_id) if t.job_id else None
    return job is not None and job.status == "waiting"


def submit_text(session: Session, task_id: int, text: str) -> ManualTask:
    t = _get_task(session, task_id)
    if t.kind != "text":
        raise TaskStateError("this task expects an image")
    if t.status != "pending" and not (t.status == "done" and _job_waiting(session, t)):
        raise TaskStateError("this task is already answered")
    data = validate_text(t, text)
    t.answer_text = json.dumps(data, ensure_ascii=False)
    t.status = "done"
    t.answered_at = utcnow()
    session.commit()
    resume_if_ready(t.job_id)
    return t


# ------------------------------------------------------------- image tasks


@dataclass
class ImageReq:
    prompt: str
    label: str = ""
    refs: list[str] = field(default_factory=list)  # stored file paths (data dir relative)
    size: tuple[int, int] = (1024, 1024)
    seed: int | None = None
    skippable: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


def image_batch(book_id: int, task: str, items: list[ImageReq], *, group: str = "", provider_name: str | None = None,
                stable: bool = False, min_done: int = 0,
                progress: Callable[[float, str | None], None] | None = None) -> list[bytes | None]:
    """API mode: generate every item with the image provider. Manual mode:
    return the stored answers, or create ALL missing tasks at once and raise
    AwaitingManual. Skipped items come back as None."""
    if not items:
        return []
    if not is_manual():
        from ..providers.registry import get_image_provider

        provider = get_image_provider(provider_name or None)
        out: list[bytes | None] = []
        for i, it in enumerate(items):
            refs = [d for d in (storage.read_bytes(p) for p in it.refs) if d]
            out.append(provider.generate(it.prompt, it.size, reference_images=refs, seed=it.seed))
            if progress:
                progress((i + 1) / len(items), it.label or None)
        return out

    job_id, _ = _ctx()
    keys = [task_key("image", task, it.prompt, it.seed, *([] if stable else [job_id])) for it in items]
    with SessionLocal() as s:
        existing = {t.key: t for t in s.scalars(select(ManualTask).where(ManualTask.book_id == book_id,
                                                                          ManualTask.key.in_(keys))).all()}
        waiting: list[ManualTask] = []
        results: list[bytes | None] = []
        for it, k in zip(items, keys):
            t = existing.get(k)
            if t is None:
                t = ManualTask(book_id=book_id, job_id=job_id, kind="image", task=task, key=k, group=group or task,
                               title=f"{task} {it.label}".strip(), prompt=it.prompt, status="pending",
                               meta=_jsonable({"label": it.label, "refs": [r for r in it.refs if r], "size": list(it.size),
                                               "skippable": it.skippable, "min_done": min_done, **it.meta}))
                s.add(t)
                existing[k] = t
                waiting.append(t)
            elif t.status == "pending":
                if t.job_id != job_id:
                    t.job_id = job_id
                if t not in waiting:
                    waiting.append(t)
            elif t.status == "skipped":
                results.append(None)
            else:
                results.append(storage.read_bytes(t.answer_path))
        if waiting:
            s.commit()
            raise AwaitingManual([t.id for t in waiting])
    return results


def _store_image(session: Session, t: ManualTask, data: bytes) -> None:
    from .uploads import validate_image

    data, ext = validate_image(data, max_bytes=MAX_ANSWER_IMAGE_BYTES)
    path = storage.sub(t.book_id, "manual") / f"task_{t.id}.{ext}"
    path.write_bytes(data)
    t.answer_path = storage.rel(path)
    t.status = "done"
    t.answered_at = utcnow()


def _check_image_task(session: Session, t: ManualTask) -> None:
    if t.kind != "image":
        raise TaskStateError("this task expects a JSON answer")
    if t.status != "pending" and not (t.status == "done" and _job_waiting(session, t)):
        raise TaskStateError("this task is already answered")


def submit_image(session: Session, task_id: int, data: bytes) -> ManualTask:
    t = _get_task(session, task_id)
    _check_image_task(session, t)
    _store_image(session, t, data)
    session.commit()
    resume_if_ready(t.job_id)
    return t


def skip(session: Session, task_id: int) -> ManualTask:
    t = _get_task(session, task_id)
    if t.status != "pending":
        raise TaskStateError("only open tasks can be skipped")
    meta = t.meta or {}
    if t.kind != "image" or not meta.get("skippable", True):
        raise TaskStateError("this task cannot be skipped")
    min_done = int(meta.get("min_done") or 0)
    if min_done:
        others = session.scalars(select(ManualTask).where(ManualTask.job_id == t.job_id, ManualTask.task == t.task,
                                                          ManualTask.group == t.group, ManualTask.id != t.id)).all()
        if sum(1 for o in others if o.status != "skipped") < min_done:
            raise TaskStateError(f"at least {min_done} image(s) of this group are needed")
    t.status = "skipped"
    t.answered_at = utcnow()
    session.commit()
    resume_if_ready(t.job_id)
    return t


# ---------------------------------------------------------------- listing


def open_tasks(session: Session, book_id: int, kind: str | None = None) -> list[ManualTask]:
    """Pending tasks of jobs that are still active (a cancelled job's tasks are hidden)."""
    rows = session.scalars(select(ManualTask).where(ManualTask.book_id == book_id, ManualTask.status == "pending")
                           .order_by(ManualTask.id)).all()
    active_jobs = {j.id for j in session.scalars(select(Job).where(Job.book_id == book_id, Job.status.in_(ACTIVE_STATUSES))).all()}
    return [t for t in rows if (t.job_id is None or t.job_id in active_jobs) and (kind is None or t.kind == kind)]


def recent_tasks(session: Session, book_id: int, limit: int = 12) -> list[ManualTask]:
    return list(session.scalars(select(ManualTask).where(ManualTask.book_id == book_id, ManualTask.status != "pending")
                                .order_by(ManualTask.answered_at.desc(), ManualTask.id.desc()).limit(limit)).all())


_PAGE_NO = re.compile(r"(?:page|pg|p|img|image)[\s_\-#]*(\d{1,4})(?!\d)", re.I)


def number_in_filename(name: str) -> str | None:
    """`page_12.png` / `12.png` -> "12". Other numbers (dates, times in
    ChatGPT's default file names) are ignored on purpose."""
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", os.path.basename(name or "")).strip()
    if re.fullmatch(r"\d{1,4}", stem):
        return str(int(stem))
    m = _PAGE_NO.search(stem)
    return str(int(m.group(1))) if m else None


def bulk_images(session: Session, book_id: int, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    """Match uploaded files to open image tasks: by the number in the file name
    (task label), else in order. Returns what was matched."""
    pending = open_tasks(session, book_id, kind="image")
    by_label: dict[str, list[ManualTask]] = {}
    for t in pending:
        by_label.setdefault(str((t.meta or {}).get("label", "")), []).append(t)
    assigned: dict[int, tuple[str, bytes, ManualTask]] = {}
    leftovers: list[tuple[int, str, bytes]] = []
    for i, (name, data) in enumerate(files):
        num = number_in_filename(name)
        cands = [t for t in by_label.get(num or "", []) if t.id not in {a[2].id for a in assigned.values()}]
        if num and cands:
            assigned[i] = (name, data, cands[0])
        else:
            leftovers.append((i, name, data))
    used = {a[2].id for a in assigned.values()}
    free = [t for t in pending if t.id not in used]
    unmatched: list[str] = []
    for i, name, data in leftovers:
        if free:
            assigned[i] = (name, data, free.pop(0))
        else:
            unmatched.append(name)
    matched, errors, jobs = [], [], set()
    for i in sorted(assigned):
        name, data, t = assigned[i]
        try:
            _store_image(session, t, data)
        except ValueError as e:
            errors.append(f"{name}: {e}")
            continue
        matched.append({"file": name, "task_id": t.id, "label": (t.meta or {}).get("label", "")})
        jobs.add(t.job_id)
    session.commit()
    for jid in jobs:
        resume_if_ready(jid)
    return {"matched": matched, "unmatched": unmatched, "errors": errors}
