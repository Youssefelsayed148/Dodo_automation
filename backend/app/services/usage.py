"""UsageLog sink + cost summaries (PLAN.md section 18)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Page, UsageLog
from ..providers.base import UsageRecord, add_usage_sink


def db_sink(rec: UsageRecord) -> None:
    with SessionLocal() as s:
        s.add(UsageLog(provider=rec.provider, model=rec.model, kind=rec.kind, units=rec.units,
                       est_cost_usd=rec.est_cost_usd, book_id=rec.book_id, page_id=rec.page_id,
                       purpose=rec.purpose))
        s.commit()


def install() -> None:
    add_usage_sink(db_sink)


def book_cost(session: Session, book_id: int) -> float:
    v = session.scalar(select(func.coalesce(func.sum(UsageLog.est_cost_usd), 0.0)).where(UsageLog.book_id == book_id))
    return float(v or 0.0)


def book_summary(session: Session, book_id: int) -> dict[str, Any]:
    rows = session.scalars(select(UsageLog).where(UsageLog.book_id == book_id)).all()
    by_kind: dict[str, float] = defaultdict(float)
    by_purpose: dict[str, float] = defaultdict(float)
    per_page: dict[int, dict[str, float]] = defaultdict(lambda: {"cost": 0.0, "calls": 0, "images": 0})
    for r in rows:
        by_kind[r.kind] += r.est_cost_usd
        by_purpose[r.purpose or "other"] += r.est_cost_usd
        if r.page_id is not None:
            pp = per_page[r.page_id]
            pp["cost"] += r.est_cost_usd
            pp["calls"] += 1
            if r.kind == "image":
                pp["images"] += 1
    pages = session.scalars(select(Page).where(Page.book_id == book_id).order_by(Page.index)).all()
    page_rows = []
    for p in pages:
        pp = per_page.get(p.id, {"cost": 0.0, "calls": 0, "images": 0})
        page_rows.append({"page_id": p.id, "index": p.index, "type": p.type, "attempts": p.attempts,
                          "redone": max(0, int(pp["images"]) - 1), "cost": round(pp["cost"], 4),
                          "images": int(pp["images"])})
    total = sum(r.est_cost_usd for r in rows)
    image_pages = [r for r in page_rows if r["images"]]
    return {
        "total_usd": round(total, 4),
        "by_kind": {k: round(v, 4) for k, v in by_kind.items()},
        "by_purpose": {k: round(v, 4) for k, v in by_purpose.items()},
        "calls": len(rows),
        "pages": page_rows,
        "avg_per_image_page": round(sum(r["cost"] for r in image_pages) / len(image_pages), 4) if image_pages else 0.0,
        "total_redos": sum(r["redone"] for r in page_rows),
    }
