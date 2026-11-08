"""Persistent job runner (DB-backed, no Redis).

- Jobs are rows in `jobs`. The worker loop picks `queued` rows and runs the
  registered handler in a thread.
- Handlers get a JobContext to report progress and check for cancellation.
- On startup, jobs left `running` by a crash/restart go back to `queued`, so
  work resumes. Handlers are written to be idempotent (skip finished work).
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Job, utcnow

log = logging.getLogger(__name__)

Handler = Callable[["JobContext"], dict[str, Any] | None]
HANDLERS: dict[str, Handler] = {}
_claim_lock = threading.Lock()


class JobCancelled(Exception):
    pass


class JobStopped(Exception):
    """Handler stopped on purpose (e.g. cost ceiling). Job ends `cancelled`
    with a message and can be resumed by retrying."""


def handler(job_type: str) -> Callable[[Handler], Handler]:
    def deco(fn: Handler) -> Handler:
        HANDLERS[job_type] = fn
        return fn

    return deco


class JobContext:
    def __init__(self, job_id: int, job_type: str, payload: dict[str, Any], book_id: int | None):
        self.job_id = job_id
        self.type = job_type
        self.payload = payload or {}
        self.book_id = book_id
        self._last_progress = -1.0

    def session(self) -> Session:
        return SessionLocal()

    def progress(self, value: float, message: str | None = None, **result: Any) -> None:
        value = max(0.0, min(1.0, float(value)))
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            if job is None:
                return
            job.progress = value
            if message is not None:
                job.message = message
            if result:
                job.result = {**(job.result or {}), **result}
            s.commit()
        self._last_progress = value

    def is_cancelled(self) -> bool:
        with SessionLocal() as s:
            job = s.get(Job, self.job_id)
            return job is None or job.status == "cancelled"

    def check_cancel(self) -> None:
        if self.is_cancelled():
            raise JobCancelled()


def enqueue(session: Session, job_type: str, payload: dict[str, Any] | None = None, book_id: int | None = None,
            commit: bool = True) -> Job:
    if job_type not in HANDLERS:
        from . import handlers  # noqa: F401  (ensure registration)
    if job_type not in HANDLERS:
        raise KeyError(f"no handler registered for job type '{job_type}'")
    job = Job(type=job_type, payload=payload or {}, book_id=book_id, status="queued", progress=0.0)
    session.add(job)
    if commit:
        session.commit()
        session.refresh(job)
    else:
        session.flush()
    return job


def active_job(session: Session, book_id: int, job_type: str) -> Job | None:
    return session.scalar(
        select(Job).where(Job.book_id == book_id, Job.type == job_type, Job.status.in_(("queued", "running")))
        .order_by(Job.id.desc())
    )


def retry(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status not in ("failed", "cancelled"):
        raise ValueError(f"only failed or cancelled jobs can be retried (status is {job.status})")
    job.status = "queued"
    job.error = None
    job.progress = 0.0
    job.message = "retrying"
    session.commit()
    return job


def cancel(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise KeyError(job_id)
    if job.status in ("queued", "running"):
        job.status = "cancelled"
        job.message = "cancelled by user"
        session.commit()
    return job


def recover_interrupted() -> int:
    """Put jobs that were `running` when the process died back in the queue."""
    with SessionLocal() as s:
        jobs = s.scalars(select(Job).where(Job.status == "running")).all()
        for j in jobs:
            j.status = "queued"
            j.message = "resumed after restart"
        s.commit()
        return len(jobs)


def claim_next() -> int | None:
    with _claim_lock, SessionLocal() as s:
        job = s.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1))
        if job is None:
            return None
        job.status = "running"
        job.attempts = (job.attempts or 0) + 1
        job.updated_at = utcnow()
        s.commit()
        return job.id


def run_job(job_id: int) -> str:
    """Execute one (already claimed) job synchronously. Returns final status."""
    from . import handlers  # noqa: F401

    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if job is None:
            return "missing"
        ctx = JobContext(job.id, job.type, dict(job.payload or {}), job.book_id)
        fn = HANDLERS.get(job.type)
    if fn is None:
        _finish(job_id, "failed", error=f"no handler for job type '{ctx.type}'")
        return "failed"
    try:
        result = fn(ctx) or {}
    except JobCancelled:
        _finish(job_id, "cancelled", message="cancelled")
        return "cancelled"
    except JobStopped as e:
        _finish(job_id, "cancelled", message=str(e))
        return "cancelled"
    except Exception as e:  # noqa: BLE001 - errors are stored on the job
        log.error("job %s (%s) failed: %s\n%s", job_id, ctx.type, e, traceback.format_exc())
        _finish(job_id, "failed", error=f"{type(e).__name__}: {e}")
        return "failed"
    if ctx.is_cancelled():
        return "cancelled"
    _finish(job_id, "done", result=result, progress=1.0, message="done")
    return "done"


def _finish(job_id: int, status: str, *, error: str | None = None, result: dict | None = None,
            progress: float | None = None, message: str | None = None) -> None:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if job is None:
            return
        if job.status == "cancelled" and status == "done":
            return
        job.status = status
        if error is not None:
            job.error = error[:4000]
        if result:
            job.result = {**(job.result or {}), **result}
        if progress is not None:
            job.progress = progress
        if message is not None:
            job.message = message
        s.commit()


def run_pending_sync(max_jobs: int = 1000) -> int:
    """Run queued jobs inline until the queue is empty (tests / CLI)."""
    n = 0
    while n < max_jobs:
        jid = claim_next()
        if jid is None:
            break
        run_job(jid)
        n += 1
    return n


class Worker:
    """Async loop running up to `parallel` jobs at a time in threads."""

    def __init__(self, parallel: int = 2, poll_interval: float = 0.5):
        self.parallel = parallel
        self.poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._running: set[asyncio.Task] = set()

    async def _loop(self) -> None:
        recovered = recover_interrupted()
        if recovered:
            log.info("resumed %d interrupted job(s)", recovered)
        while not self._stop.is_set():
            try:
                while len(self._running) < self.parallel:
                    jid = await asyncio.to_thread(claim_next)
                    if jid is None:
                        break
                    t = asyncio.create_task(asyncio.to_thread(run_job, jid))
                    self._running.add(t)
                    t.add_done_callback(self._running.discard)
            except Exception:  # pragma: no cover
                log.exception("worker loop error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None
