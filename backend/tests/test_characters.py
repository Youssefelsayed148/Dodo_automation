from .conftest import needs_api
from .helpers import approve_characters, themed_book, wait_ok

pytestmark = needs_api


def _char(client, bid, cid):
    return next(c for c in client.get(f"/api/books/{bid}/characters").json()["characters"] if c["id"] == cid)


def test_full_character_flow_and_gates(client):
    b = themed_book(client)
    bid = b["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": 2}).json())
    chars = client.get(f"/api/books/{bid}/characters").json()["characters"]
    assert len(chars) == 2 and all(c["signature_feature"] for c in chars)
    cid = chars[0]["id"]

    # gates: cannot edit/sheet/approve before the previous step
    assert client.post(f"/api/books/{bid}/characters/{cid}/edit", json={"instruction": "x"}).status_code == 409
    assert client.post(f"/api/books/{bid}/characters/{cid}/sheet").status_code == 409
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).status_code == 409

    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/candidates").json())
    c = _char(client, bid, cid)
    cands = [a for a in c["assets"] if a["kind"] == "candidate"]
    assert len(cands) == 4
    client.post(f"/api/books/{bid}/characters/{cid}/select/{cands[2]['id']}")
    style = client.get(f"/api/books/{bid}/characters").json()["style_anchor"]
    assert style["reference_url"] and style["rules"]

    # lock and edit keeps history
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/edit", json={"instruction": "shorter ears"}).json())
    c = _char(client, bid, cid)
    edits = [v for v in c["versions"] if v["kind"] == "edit"]
    assert edits and edits[-1]["instruction"] == "shorter ears" and edits[-1]["parent_id"] == cands[2]["id"]
    sel = [a for a in c["assets"] if a["kind"] == "candidate" and a["selected"]]
    assert len(sel) == 1 and sel[0]["meta"]["parent_id"] == cands[2]["id"]
    assert "shorter ears" in sel[0]["meta"]["prompt"]

    # revert to an older version
    client.post(f"/api/books/{bid}/characters/{cid}/select/{cands[2]['id']}")
    client.post(f"/api/books/{bid}/characters/{cid}/select/{sel[0]['id']}")

    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/sheet").json())
    c = _char(client, bid, cid)
    assert {a["meta"].get("view") for a in c["assets"] if a["kind"] == "sheet"} == {"front", "side", "three-quarter"}
    assert {a["meta"].get("expression") for a in c["assets"] if a["kind"] == "expression"} == {"happy", "sleepy", "surprised"}

    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/consistency").json())
    c = _char(client, bid, cid)
    assert c["consistency"]["pass"] and len(c["consistency"]["results"]) == 3
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).json()["status"] == "approved"

    # sample page is blocked until every character is approved
    assert client.post(f"/api/books/{bid}/sample").status_code == 409
    gates = client.get(f"/api/books/{bid}/characters").json()["gates"]
    assert gates["characters_approved"] == 1 and not gates["characters_ok"]


def test_consistency_failure_needs_override(client):
    from app.providers import registry
    from app.providers.mock import MockVisionLLM

    b = themed_book(client)
    bid = b["id"]
    registry.set_override("vision", MockVisionLLM({"consistency_check": {"pass": False, "issues": ["signature feature missing"], "checks": {}}}))
    wait_ok(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": 1}).json())
    cid = client.get(f"/api/books/{bid}/characters").json()["characters"][0]["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/candidates").json())
    cand = [a for a in _char(client, bid, cid)["assets"] if a["kind"] == "candidate"][0]
    client.post(f"/api/books/{bid}/characters/{cid}/select/{cand['id']}")
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/sheet").json())
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/consistency").json())
    c = _char(client, bid, cid)
    assert c["consistency"]["pass"] is False
    assert "signature feature missing" in c["consistency"]["results"][0]["issues"]
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).status_code == 409
    r = client.post(f"/api/books/{bid}/characters/{cid}/approve", json={"override": True})
    assert r.status_code == 200 and r.json()["consistency"]["override"] is True


def test_sample_gate_blocks_generation_and_library_reuse(client):
    b = themed_book(client)
    bid = b["id"]
    chars = approve_characters(client, bid)
    wait_ok(client, client.post(f"/api/books/{bid}/plan").json())
    assert client.post(f"/api/books/{bid}/generate").status_code == 409  # sample not approved
    wait_ok(client, client.post(f"/api/books/{bid}/sample").json())
    assert client.get(f"/api/books/{bid}").json()["sample"]["status"] == "pending"
    client.post(f"/api/books/{bid}/sample/approve")
    assert client.get(f"/api/books/{bid}/characters").json()["gates"]["sample_ok"]

    # library
    cid = chars[0]["id"]
    assert client.post(f"/api/books/{bid}/characters/{cid}/library").json()["in_library"]
    lib = client.get("/api/library").json()
    assert [c["id"] for c in lib] == [cid]
    b2 = themed_book(client)
    r = client.post(f"/api/books/{b2['id']}/characters/from-library/{cid}")
    assert r.status_code == 200
    copy = r.json()
    assert copy["status"] == "approved" and copy["book_id"] == b2["id"] and copy["id"] != cid
    assert len(copy["assets"]) == len(chars[0]["assets"])
    assert all(client.get(a["url"]).status_code == 200 for a in copy["assets"])
