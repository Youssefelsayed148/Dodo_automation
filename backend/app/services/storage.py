"""Filesystem layout under data/books/<id>/."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..config import get_settings


def book_dir(book_id: int) -> Path:
    d = get_settings().books_dir / str(book_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sub(book_id: int, name: str) -> Path:
    d = book_dir(book_id) / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def source_dir(book_id: int) -> Path:
    return sub(book_id, "source")


def pages_dir(book_id: int) -> Path:
    return sub(book_id, "pages")


def raw_dir(book_id: int) -> Path:
    return sub(book_id, "raw")


def characters_dir(book_id: int | None) -> Path:
    if book_id is None:
        d = get_settings().library_dir
        d.mkdir(parents=True, exist_ok=True)
        return d
    return sub(book_id, "characters")


def export_dir(book_id: int) -> Path:
    return sub(book_id, "export")


def rel(path: Path) -> str:
    """Store paths relative to the data dir (portable between machines)."""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(get_settings().data_dir))
    except ValueError:
        return str(p)


def abs_path(stored: str | None) -> Path | None:
    if not stored:
        return None
    p = Path(stored)
    return p if p.is_absolute() else get_settings().data_dir / p


def read_bytes(stored: str | None) -> bytes | None:
    p = abs_path(stored)
    return p.read_bytes() if p and p.is_file() else None


def thumb_for(stored: str) -> Path:
    """Cached thumbnail location next to the image (in a `_thumbs` folder)."""
    p = abs_path(stored)
    assert p is not None
    return p.parent / "_thumbs" / f"{p.stem}.png"


def delete_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


_SAFE = re.compile(r"[^A-Za-z0-9؀-ۿ _.()\-]+")


def safe_filename(name: str, default: str = "book") -> str:
    name = _SAFE.sub("", name or "").strip(" .")
    return name[:120] or default
