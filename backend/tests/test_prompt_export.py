import json

from .conftest import needs_api
from .helpers import ready_book

pytestmark = needs_api


def test_round_trip_export_import(client):
    b = ready_book(client, page_count=16)
    bid = b["id"]
    data = client.get(f"/api/books/{bid}/prompts").json()
    pp = data["planning_prompt"]
    assert "ORIGINALITY RULE" in pp and "LINE-ART RULES" in pp and '"pages"' in pp
    assert data["brief"]["characters"]
    from app.db import SessionLocal
    from app.models import Book
    from app.services.export_prompts import pages_as_import

    with SessionLocal() as s:
        exported = pages_as_import(s.get(Book, bid))
    before = client.get(f"/api/books/{bid}/pages").json()
    r = client.post(f"/api/books/{bid}/prompts/import", json={"text": json.dumps({"pages": exported}), "apply": False})
    assert r.status_code == 200 and r.json()["diff"]["changed"] == 0
    r = client.post(f"/api/books/{bid}/prompts/import", json={"text": json.dumps({"pages": exported}), "apply": True})
    after = client.get(f"/api/books/{bid}/pages").json()
    def strip(ps):
        return [(p["index"], p["type"], p["description"], json.dumps(p["text_content"], sort_keys=True)) for p in ps]

    assert strip(before) == strip(after)


def test_import_numbered_list_and_errors(client):
    b = ready_book(client, page_count=8)
    bid = b["id"]
    text = "Here you go:\n1. [scene] Pip waters flowers\n2. [maze] garden maze\n3. Mila reads a book\n"
    r = client.post(f"/api/books/{bid}/prompts/import", json={"text": text, "apply": True})
    assert r.status_code == 200
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert [p["type"] for p in pages][2:5] == ["scene", "maze", pages[4]["type"]]
    bad = client.post(f"/api/books/{bid}/prompts/import", json={"text": json.dumps({"pages": [{"type": "unicorn", "description": "x"}]})})
    assert bad.status_code == 422
    errs = bad.json()["detail"]["errors"]
    assert "page 1" in errs[0] and "unknown page type" in errs[0]


def test_batch_splitting(client):
    b = ready_book(client, page_count=30)
    bid = b["id"]
    n_image = sum(1 for p in client.get(f"/api/books/{bid}/pages").json() if p["is_image"])
    for size in (5, 10):
        batches = client.get(f"/api/books/{bid}/prompts?batch_size={size}").json()["batches"]
        assert all(len(x["page_ids"]) <= size for x in batches)
        assert sum(len(x["page_ids"]) for x in batches) == n_image
        assert all("No text" in x["text"] and "character sheet" in x["text"] for x in batches)
    assert client.get(f"/api/books/{bid}/prompts?batch_size=7").status_code == 422
    md = client.get(f"/api/books/{bid}/prompts.md").text
    assert md.startswith("# ") and "## Planning prompt" in md
