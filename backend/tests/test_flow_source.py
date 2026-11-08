import io

from PIL import Image

from .conftest import needs_api
from .helpers import analyzed_book, new_book, wait_ok

pytestmark = needs_api


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_settings_api(client):
    r = client.get("/api/settings").json()
    assert r["values"]["batch_size"] == 10
    assert client.put("/api/settings", json={"batch_size": 5}).json()["values"]["batch_size"] == 5
    assert client.put("/api/settings", json={"batch_size": 3}).status_code == 422


def test_text_source_produces_editable_recipe(client):
    b = analyzed_book(client)
    assert b["status"] == "analyzed"
    rec = b["recipe"]
    assert rec["confidence"] in ("medium", "low") and rec["mood"]
    assert sum(m["share"] for m in rec["page_mix"]) == 100
    r = client.put(f"/api/books/{b['id']}/recipe", json={"mood": "calm", "age_group": "2-4"})
    assert r.json()["mood"] == "calm" and r.json()["age_group"] == "2-4"


def test_uploads_give_high_confidence_and_are_deleted(client, isolated_env):
    from app.services import storage

    b = new_book(client)
    buf = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(buf, format="PNG")
    r = client.post(f"/api/books/{b['id']}/source", data={"text": "x"},
                    files=[("files", ("p1.png", buf.getvalue(), "image/png"))])
    assert r.status_code == 200, r.text
    assert any(storage.source_dir(b["id"]).iterdir())
    wait_ok(client, r.json()["job"])
    book = client.get(f"/api/books/{b['id']}").json()
    assert book["recipe"]["confidence"] == "high"
    assert not any(storage.source_dir(b["id"]).iterdir()), "source images must be deleted after analysis"


def test_bad_upload_rejected(client):
    b = new_book(client)
    r = client.post(f"/api/books/{b['id']}/source", files=[("files", ("x.png", b"not an image", "image/png"))])
    assert r.status_code == 422


def test_blocked_url_rejected(client):
    b = new_book(client)
    r = client.post(f"/api/books/{b['id']}/source", data={"url": "http://127.0.0.1:8000/admin"})
    assert r.status_code == 422


def test_thin_page_reports_fallback(client, monkeypatch):
    from app.services import analysis
    from app.services.url_fetch import PageInfo

    monkeypatch.setattr(analysis, "fetch_page", lambda url: PageInfo(url=url, title="Robot check"))
    monkeypatch.setattr("app.api.books.validate_url", lambda url: url)
    b = new_book(client)
    r = client.post(f"/api/books/{b['id']}/source", data={"url": "https://shop.example.com/x"})
    job = wait_ok(client, r.json()["job"])
    assert job["result"]["fetch_status"] == "thin"
    book = client.get(f"/api/books/{b['id']}").json()
    assert book["fetch"]["status"] == "thin"
    assert book["recipe"]["confidence"] == "low"


def test_originality_scrub(client, monkeypatch):
    from app.providers import registry
    from app.providers.mock import MockTextLLM, MockVisionLLM
    from app.services import analysis
    from app.services.url_fetch import PageInfo

    info = PageInfo(url="u", title="Bramble Bunny Bakery", description="Join Bramble Bunny in cozy bakery scenes " * 3)
    info.brand_terms = ["Sunnyday Press", "Bramble Bunny Bakery"]
    monkeypatch.setattr(analysis, "fetch_page", lambda url: info)
    monkeypatch.setattr("app.api.books.validate_url", lambda url: url)
    leaky = {"mood": "cozy like Bramble", "age_group": "4-8", "line_weight": "bold", "detail_level": "low",
             "page_mix": [{"type": "scene", "share": 100}], "confidence": "medium", "notes": "Bramble Bunny style by Sunnyday"}
    registry.set_override("text", MockTextLLM({"analyze_source": leaky}))
    registry.set_override("vision", MockVisionLLM({"analyze_source": leaky}))
    b = new_book(client)
    wait_ok(client, client.post(f"/api/books/{b['id']}/source", data={"url": "https://shop.example.com/x"}).json()["job"])
    rec = client.get(f"/api/books/{b['id']}/recipe").json()
    for field in ("mood", "notes"):
        assert "Bramble" not in rec[field] and "Sunnyday" not in rec[field]
