"""Shared helpers to drive a book through the wizard with mock providers."""

from __future__ import annotations

from .conftest import run_jobs


def wait_ok(client, job: dict) -> dict:
    run_jobs()
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["status"] == "done", j
    return j


def new_book(client, **kw) -> dict:
    r = client.post("/api/books", json=kw)
    assert r.status_code == 200, r.text
    return r.json()


def analyzed_book(client, text="A cozy coloring book with cute bakery animals for ages 4-8, bold outlines.", **kw) -> dict:
    b = new_book(client, **kw)
    r = client.post(f"/api/books/{b['id']}/source", data={"text": text})
    assert r.status_code == 200, r.text
    wait_ok(client, r.json()["job"])
    return client.get(f"/api/books/{b['id']}").json()


def themed_book(client, **kw) -> dict:
    b = analyzed_book(client, **kw)
    bid = b["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/themes/propose").json())
    themes = client.get(f"/api/books/{bid}/themes").json()
    client.post(f"/api/books/{bid}/themes/choose", json={"theme_id": themes[0]["id"]})
    wait_ok(client, client.post(f"/api/books/{bid}/formats/propose").json())
    fmts = client.get(f"/api/books/{bid}/formats").json()
    r = client.post(f"/api/books/{bid}/formats/{fmts[1]['id']}/choose")
    assert r.status_code == 200, r.text
    return client.get(f"/api/books/{bid}").json()


def approve_characters(client, bid: int, count: int = 1) -> list[dict]:
    wait_ok(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": count}).json())
    chars = client.get(f"/api/books/{bid}/characters").json()["characters"]
    for c in chars:
        cid = c["id"]
        wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/candidates").json())
        c = next(x for x in client.get(f"/api/books/{bid}/characters").json()["characters"] if x["id"] == cid)
        cands = [a for a in c["assets"] if a["kind"] == "candidate"]
        assert len(cands) == 4
        assert client.post(f"/api/books/{bid}/characters/{cid}/select/{cands[1]['id']}").status_code == 200
        wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/sheet").json())
        wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/consistency").json())
        r = client.post(f"/api/books/{bid}/characters/{cid}/approve", json={})
        assert r.status_code == 200, r.text
    return client.get(f"/api/books/{bid}/characters").json()["characters"]


def ready_book(client, page_count: int = 12, **kw) -> dict:
    b = themed_book(client, **kw)
    bid = b["id"]
    approve_characters(client, bid)
    wait_ok(client, client.post(f"/api/books/{bid}/sample").json())
    assert client.post(f"/api/books/{bid}/sample/approve").status_code == 200
    client.patch(f"/api/books/{bid}", json={"page_count": page_count})
    wait_ok(client, client.post(f"/api/books/{bid}/plan").json())
    return client.get(f"/api/books/{bid}").json()
