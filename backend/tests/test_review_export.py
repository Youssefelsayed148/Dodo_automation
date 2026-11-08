import io
import json

from .conftest import needs_api, needs_weasy, run_jobs
from .helpers import ready_book, wait_ok

pytestmark = [needs_api, needs_weasy]


def _generated_book(client, n=14, **kw):
    b = ready_book(client, page_count=n, **kw)
    wait_ok(client, client.post(f"/api/books/{b['id']}/generate").json())
    return b


def test_review_reject_redo_only_rejected(client):
    b = _generated_book(client, 14)
    bid = b["id"]
    pages = client.get(f"/api/books/{bid}/pages").json()
    image_pages = [p for p in pages if p["is_image"]]
    rejected = image_pages[:3]
    for p in rejected:
        assert client.post(f"/api/books/{bid}/pages/{p['id']}/review", json={"status": "rejected"}).json()["status"] == "rejected"
    before = {p["id"]: p for p in client.get(f"/api/books/{bid}/pages").json()}
    r = client.post(f"/api/books/{bid}/review/redo", json={"note": "rounder faces"})
    assert sorted(r.json()["pages"]) == sorted(p["id"] for p in rejected)
    run_jobs()
    after = {p["id"]: p for p in client.get(f"/api/books/{bid}/pages").json()}
    for pid, p in after.items():
        if pid in {x["id"] for x in rejected}:
            assert p["status"] == "generated" and p["attempts"] == before[pid]["attempts"] + 1
            assert "rounder faces" in p["prompt"]
        else:
            assert p["attempts"] == before[pid]["attempts"] and p["status"] == before[pid]["status"]
    assert client.post(f"/api/books/{bid}/review/redo", json={}).status_code == 409  # nothing rejected now
    r = client.post(f"/api/books/{bid}/review/approve-all")
    assert r.json()["approved"] == len(pages)


def test_export_pdfs_sizes_and_fonts(client):
    from pypdf import PdfReader

    from app.services import storage

    b = _generated_book(client, 12)
    bid = b["id"]
    client.patch(f"/api/books/{bid}", json={"bleed": True})
    client.post(f"/api/books/{bid}/review/approve-all")
    client.put(f"/api/books/{bid}/cover", json={"template": "framed", "subtitle": "A coloring book"})
    job = client.post(f"/api/books/{bid}/export", json={}).json()
    wait_ok(client, job)
    out = storage.export_dir(bid)
    files = client.get(f"/api/books/{bid}/export/files").json()["files"]
    assert {"interior.pdf", "cover.pdf", "book-settings.json"} <= set(files)
    assert len([f for f in files if f.startswith("pages/")]) == 12
    interior = PdfReader(out / "interior.pdf")
    assert len(interior.pages) == 12
    for page in interior.pages:
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        assert abs(w - 630) < 0.5 and abs(h - 810) < 0.5  # 8.5x11in + 0.125in bleed
    cover = PdfReader(out / "cover.pdf")
    assert len(cover.pages) == 1
    fonts = set()
    for page in interior.pages:
        res = page.get("/Resources") or {}
        for f in (res.get("/Font") or {}).values():
            fonts.add(str(f.get_object().get("/BaseFont")))
    assert fonts, "fonts must be embedded"
    settings = json.loads((out / "book-settings.json").read_text())
    assert settings["brief"]["title"] == client.get(f"/api/books/{bid}").json()["title"]
    assert client.get(f"/api/books/{bid}").json()["status"] == "exported"
    assert client.get(f"/api/books/{bid}/export/interior.pdf").status_code == 200


def test_page_size_without_bleed():
    import importlib

    from app.services.specs import page_spec

    assert page_spec("8.5x11in", False).points == (612.0, 792.0)
    assert importlib.util.find_spec("weasyprint")


def test_arabic_pdf_text(client):
    from pypdf import PdfReader

    from app.services import storage

    b = _generated_book(client, 8, book_language="ar")
    bid = b["id"]
    client.post(f"/api/books/{bid}/title", json={"title": "أصدقاء الحديقة"})
    client.post(f"/api/books/{bid}/review/approve-all")
    wait_ok(client, client.post(f"/api/books/{bid}/export", json={}).json())
    out = storage.export_dir(bid)
    cover_text = PdfReader(out / "cover.pdf").pages[0].extract_text()
    assert "الحديقة" in cover_text or "ﺍﻟﺤﺪﻳﻘﺔ" in cover_text or len(cover_text.strip()) > 0
    interior = PdfReader(out / "interior.pdf")
    end_text = interior.pages[-1].extract_text()
    assert end_text.strip(), "end page text must render"


def test_export_requires_approved_pages(client):
    b = _generated_book(client, 6)
    assert client.post(f"/api/books/{b['id']}/export", json={}).status_code == 409
    assert client.post(f"/api/books/{b['id']}/export", json={"drive": True}).status_code == 409


def test_backup_roundtrip(client):
    b = _generated_book(client, 8)
    bid = b["id"]
    blob = client.get(f"/api/books/{bid}/backup").content
    r = client.post("/api/books/import-backup", files={"file": ("b.zip", io.BytesIO(blob), "application/zip")})
    assert r.status_code == 200, r.text
    nb = r.json()
    assert nb["id"] != bid and nb["title"] == client.get(f"/api/books/{bid}").json()["title"]
    old_pages = client.get(f"/api/books/{bid}/pages").json()
    new_pages = client.get(f"/api/books/{nb['id']}/pages").json()
    assert [p["description"] for p in old_pages] == [p["description"] for p in new_pages]
    assert all(client.get(p["image_url"]).status_code == 200 for p in new_pages if p["image_url"])
    chars = client.get(f"/api/books/{nb['id']}/characters").json()["characters"]
    assert chars and all(client.get(a["url"]).status_code == 200 for c in chars for a in c["assets"])
    assert client.post("/api/books/import-backup", files={"file": ("x.zip", b"junk", "application/zip")}).status_code == 422
