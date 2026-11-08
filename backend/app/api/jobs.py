from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..jobs import runner
from ..models import Job
from . import serialize as ser

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs(book_id: int | None = None, status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.id.desc()).limit(min(limit, 500))
    if book_id is not None:
        q = q.where(Job.book_id == book_id)
    if status:
        q = q.where(Job.status == status)
    return [ser.job(j) for j in db.scalars(q).all()]


@router.get("/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise HTTPException(404, "job not found")
    return ser.job(j)


@router.post("/{job_id}/retry")
def retry_job(job_id: int, db: Session = Depends(get_db)):
    try:
        return ser.job(runner.retry(db, job_id))
    except KeyError:
        raise HTTPException(404, "job not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    try:
        return ser.job(runner.cancel(db, job_id))
    except KeyError:
        raise HTTPException(404, "job not found")
