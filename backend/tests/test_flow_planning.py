from .conftest import needs_api
from .helpers import analyzed_book, themed_book, wait_ok

pytestmark = needs_api


def test_themes_formats_and_plan(client):
    b = analyzed_book(client)
    bid = b["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/themes/propose").json())
    themes = client.get(f"/api/books/{bid}/themes").json()
    assert len(themes) == 3
    r = client.post(f"/api/books/{bid}/themes/choose", json={"theme_id": themes[2]["id"], "title": "Our Garden"})
    assert r.json()["title"] == "Our Garden" and r.json()["status"] == "themed"
    client.post(f"/api/books/{bid}/title", json={"title": "Our Little Garden"})
    assert client.get(f"/api/books/{bid}").json()["title"] == "Our Little Garden"

    wait_ok(client, client.post(f"/api/books/{bid}/formats/propose").json())
    fmts = client.get(f"/api/books/{bid}/formats").json()
    assert 3 <= len(fmts) <= 4
    for f in fmts:
        assert sum(x["share"] for x in f["blocks"]) == 100
    wait_ok(client, client.post(f"/api/books/{bid}/formats/hybrid", json={"instruction": "mazes and tracing"}).json())
    assert len(client.get(f"/api/books/{bid}/formats").json()) == len(fmts) + 1

    bad = client.put(f"/api/books/{bid}/formats/{fmts[0]['id']}", json={"blocks": [{"type": "scene", "share": 90}]})
    assert bad.status_code == 422
    ok = client.post(f"/api/books/{bid}/formats/{fmts[0]['id']}/choose",
                     json={"blocks": [{"type": "scene", "share": 60}, {"type": "maze", "share": 25}, {"type": "qa_page", "share": 15}]})
    assert ok.status_code == 200, ok.text

    client.patch(f"/api/books/{bid}", json={"page_count": 24})
    wait_ok(client, client.post(f"/api/books/{bid}/plan").json())
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert len(pages) == 24
    assert pages[0]["type"] == "title_page" and pages[1]["type"] == "belongs_to_page" and pages[-1]["type"] == "end_page"
    content = pages[2:-1]
    descs = [p["description"] for p in content]
    assert len(set(descs)) == len(descs), "descriptions must be distinct"
    types = [p["type"] for p in content]
    assert types.count("scene") == 13 and types.count("maze") == 5 and types.count("qa_page") == 3
    assert all(p["text_content"].get("question") for p in content if p["type"] == "qa_page")


def test_plan_requires_format(client):
    b = analyzed_book(client)
    assert client.post(f"/api/books/{b['id']}/plan").status_code == 409


def test_allocation_helpers():
    from app.services.planning import allocate_counts, normalize_shares, order_slots

    assert sum(b["share"] for b in normalize_shares([{"type": "scene", "share": 33.3}, {"type": "maze", "share": 33.3},
                                                     {"type": "qa_page", "share": 33.3}])) == 100
    assert normalize_shares([{"type": "title_page", "share": 50}]) == [{"type": "scene", "share": 100}]
    c = allocate_counts([{"type": "scene", "share": 60}, {"type": "maze", "share": 30}, {"type": "qa_page", "share": 10}], 9)
    assert sum(c.values()) == 9 and all(v >= 1 for v in c.values())
    order = order_slots({"scene": 6, "maze": 2})
    assert order[0] == "scene" and order.count("maze") == 2 and order.index("maze") > 0


def test_duplicate_descriptions_are_fixed(client):
    from app.providers import registry
    from app.providers.mock import MockTextLLM

    def dup(prompt, meta):
        slots = meta["vars"]["slots"]
        return {"pages": [{"type": t, "description": "same scene", "characters": [], "text_content": {}} for t in slots]}

    b = themed_book(client)
    registry.set_override("text", MockTextLLM({"plan_pages": dup}))
    wait_ok(client, client.post(f"/api/books/{b['id']}/plan").json())
    pages = client.get(f"/api/books/{b['id']}/pages").json()[2:-1]
    assert len({p["description"] for p in pages}) == len(pages)
