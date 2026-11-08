"""Backup a whole book (DB rows + files) as a zip, and re-import it."""

from __future__ import annotations

import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..models import Book, Character, CharacterAsset, FormatOption, Page, Recipe, ThemeOption
from . import storage

FORMAT_VERSION = 1


def _row(obj: Any, exclude: tuple[str, ...] = ()) -> dict[str, Any]:
    out = {}
    for col in obj.__table__.columns:
        if col.name in exclude:
            continue
        v = getattr(obj, col.name)
        out[col.name] = v.isoformat() if hasattr(v, "isoformat") else v
    return out


def export_zip(session: Session, book: Book) -> bytes:
    chars = session.query(Character).filter(Character.book_id == book.id).all()
    data = {
        "format_version": FORMAT_VERSION,
        "book": _row(book),
        "recipe": _row(book.recipe) if book.recipe else None,
        "themes": [_row(t) for t in book.themes],
        "formats": [_row(f) for f in book.formats],
        "pages": [_row(p) for p in book.pages],
        "characters": [{**_row(c), "assets": [_row(a) for a in c.assets]} for c in chars],
    }
    buf = io.BytesIO()
    root = storage.book_dir(book.id)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("book.json", json.dumps(data, ensure_ascii=False, indent=2))
        for p in root.rglob("*"):
            if p.is_file() and "export" not in p.relative_to(root).parts[:1]:
                z.write(p, f"files/{p.relative_to(root)}")
    return buf.getvalue()


def _remap(path: str | None, old_id: int, new_id: int) -> str | None:
    if not path:
        return path
    prefix = f"books/{old_id}/"
    return f"books/{new_id}/" + path[len(prefix):] if path.startswith(prefix) else path


def import_zip(session: Session, blob: bytes) -> Book:
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        names = z.namelist()
        if "book.json" not in names:
            raise ValueError("not a Dodo Book Studio backup (book.json missing)")
        data = json.loads(z.read("book.json"))
        if data.get("format_version") != FORMAT_VERSION:
            raise ValueError("unsupported backup version")
        b = data["book"]
        old_id = b["id"]
        book = Book(title=b["title"], status=b["status"], source_type=b["source_type"], source_url=b["source_url"],
                    source_text=b["source_text"], book_language=b["book_language"], trim_size=b["trim_size"],
                    bleed=b["bleed"], page_count=b["page_count"], style_anchor=b.get("style_anchor") or {},
                    meta=b.get("meta") or {})
        session.add(book)
        session.flush()
        new_id = book.id
        dest = storage.book_dir(new_id)
        for n in names:
            if not n.startswith("files/") or n.endswith("/"):
                continue
            rel = Path(n[len("files/"):])
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError("unsafe path in backup")
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    sa = dict(book.style_anchor or {})
    if sa.get("reference_path"):
        sa["reference_path"] = _remap(sa["reference_path"], old_id, new_id)
    book.style_anchor = sa
    meta = dict(book.meta or {})
    for key in ("sample",):
        if isinstance(meta.get(key), dict) and meta[key].get("path"):
            meta[key] = {**meta[key], "path": _remap(meta[key]["path"], old_id, new_id)}
    book.meta = meta
    if data.get("recipe"):
        r = data["recipe"]
        session.add(Recipe(book_id=new_id, mood=r["mood"], age_group=r["age_group"], line_weight=r["line_weight"],
                           detail_level=r["detail_level"], page_mix=r["page_mix"], confidence=r["confidence"], notes=r["notes"]))
    theme_map, fmt_map, char_map = {}, {}, {}
    for t in data["themes"]:
        o = ThemeOption(book_id=new_id, title=t["title"], description=t["description"], chosen=t["chosen"])
        session.add(o)
        session.flush()
        theme_map[t["id"]] = o.id
    for f in data["formats"]:
        o = FormatOption(book_id=new_id, name=f["name"], blocks=f["blocks"], description=f["description"], chosen=f["chosen"])
        session.add(o)
        session.flush()
        fmt_map[f["id"]] = o.id
    book.theme_id = theme_map.get(b.get("theme_id"))
    book.format_id = fmt_map.get(b.get("format_id"))
    chars_root = storage.book_dir(new_id) / "characters"
    staged = storage.book_dir(new_id) / "_characters_import"
    if chars_root.is_dir():
        chars_root.rename(staged)
    for c in data["characters"]:
        nc = Character(book_id=new_id, name=c["name"], species=c["species"], personality=c["personality"],
                       signature_feature=c["signature_feature"], proportions=c["proportions"], brief=c["brief"],
                       status=c["status"], in_library=False)
        session.add(nc)
        session.flush()
        char_map[c["id"]] = nc.id
        old_dir = f"books/{new_id}/characters/{c['id']}/"
        new_dir = f"books/{new_id}/characters/{nc.id}/"
        src_dir = staged / str(c["id"])
        dst_dir = chars_root / str(nc.id)
        if src_dir.is_dir():
            dst_dir.parent.mkdir(parents=True, exist_ok=True)
            src_dir.rename(dst_dir)
        for a in c["assets"]:
            p = _remap(a["path"], old_id, new_id) or ""
            p = p.replace(old_dir, new_dir)
            nc.assets.append(CharacterAsset(kind=a["kind"], path=p, selected=a["selected"], meta=a["meta"]))
    shutil.rmtree(staged, ignore_errors=True)
    for p in data["pages"]:
        meta = dict(p.get("meta") or {})
        meta["characters"] = [char_map[c] for c in meta.get("characters", []) if c in char_map]
        session.add(Page(book_id=new_id, index=p["index"], type=p["type"], prompt=p["prompt"], text_content=p["text_content"],
                         status=p["status"], image_path=_remap(p["image_path"], old_id, new_id), qa=p["qa"],
                         attempts=p["attempts"], batch_no=p["batch_no"], description=p["description"], meta=meta))
    session.commit()
    session.refresh(book)
    return book
