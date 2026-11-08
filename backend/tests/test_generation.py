from .conftest import needs_api, needs_weasy, run_jobs
from .helpers import ready_book, wait_ok

pytestmark = [needs_api, needs_weasy]


def test_forty_page_book_generates_and_resumes_after_restart(client):
    from app.jobs import runner
    from app.models import Job, Page

    b = ready_book(client, page_count=40)
    bid = b["id"]
    job = client.post(f"/api/books/{bid}/generate").json()
    # simulate: worker picks it up, does one page, then the process dies
    jid = runner.claim_next()
    assert jid == job["id"]
    from app.db import SessionLocal
    from app.services.generation import generate_one

    with SessionLocal() as s:
        first = s.query(Page).filter(Page.book_id == bid, Page.status == "queued").order_by(Page.index).first()
    assert generate_one(first.id, 2, True) == "generated"
    assert runner.recover_interrupted() == 1  # restart: job back to queued
    run_jobs()
    with SessionLocal() as s:
        assert s.get(Job, jid).status == "done"
        pages = s.query(Page).filter(Page.book_id == bid).order_by(Page.index).all()
        assert len(pages) == 40
        assert all(p.status == "generated" for p in pages), [(p.index, p.status, p.qa) for p in pages if p.status != "generated"]
        assert all(p.image_path for p in pages)
        # the first page was not generated twice
        again = s.get(Page, first.id)
        assert again.attempts == 1
    status = client.get(f"/api/books/{bid}/generate/status").json()
    assert status["counts"] == {"generated": 40}
    assert client.get(f"/api/books/{bid}").json()["status"] == "review"
    # thumbnails are served
    p = client.get(f"/api/books/{bid}/pages").json()[5]
    assert client.get(p["thumb_url"]).status_code == 200


def test_qa_failures_auto_redo_then_fail(client):
    from app.db import SessionLocal
    from app.providers import registry
    from app.providers.mock import MockVisionLLM
    from app.services import settings_service

    b = ready_book(client, page_count=8)
    bid = b["id"]
    calls = {"n": 0}

    def flaky(prompt, meta):
        calls["n"] += 1
        return {"pass": False, "issues": ["shading present"], "checks": {}}

    registry.set_override("vision", MockVisionLLM({"qa_vision_check": flaky}))
    with SessionLocal() as s:
        settings_service.set_many(s, {"max_redo": 2})
    wait_ok(client, client.post(f"/api/books/{bid}/generate").json())
    pages = client.get(f"/api/books/{bid}/pages").json()
    image_pages = [p for p in pages if p["is_image"]]
    assert image_pages and all(p["status"] == "failed" and p["attempts"] == 3 for p in image_pages)
    assert all(p["image_url"] for p in image_pages)  # last attempt kept for review
    assert "shading present" in image_pages[0]["prompt"]  # issues appended to the redo prompt
    assert calls["n"] == 3 * len(image_pages)
    assert all(p["status"] == "generated" for p in pages if not p["is_image"])


def test_cost_ceiling_pauses_generation(client):
    from app.db import SessionLocal
    from app.models import UsageLog
    from app.services import settings_service

    b = ready_book(client, page_count=10)
    bid = b["id"]
    with SessionLocal() as s:
        settings_service.set_many(s, {"cost_ceiling_usd": 0.5, "batch_size": 5})
        s.add(UsageLog(provider="x", model="y", kind="image", units=1, est_cost_usd=1.0, book_id=bid))
        s.commit()
    job = client.post(f"/api/books/{bid}/generate").json()
    run_jobs()
    j = client.get(f"/api/jobs/{job['id']}").json()
    assert j["status"] == "cancelled" and "cost ceiling" in j["message"]
    with SessionLocal() as s:
        settings_service.set_many(s, {"cost_ceiling_usd": 0})
    client.post(f"/api/jobs/{job['id']}/retry")
    run_jobs()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
    cost = client.get(f"/api/books/{bid}/cost").json()
    assert cost["total_usd"] >= 1.0 and len(cost["pages"]) == 10


def test_batches_and_per_page_regenerate(client):
    from app.db import SessionLocal
    from app.services import settings_service

    b = ready_book(client, page_count=12)
    bid = b["id"]
    with SessionLocal() as s:
        settings_service.set_many(s, {"batch_size": 5})
    wait_ok(client, client.post(f"/api/books/{bid}/generate").json())
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert max(p["batch_no"] for p in pages) == 3
    target = next(p for p in pages if p["is_image"])
    wait_ok(client, client.post(f"/api/books/{bid}/pages/{target['id']}/regenerate", json={"note": "bigger tree"}).json())
    after = client.get(f"/api/books/{bid}/pages/{target['id']}").json()
    assert after["attempts"] == target["attempts"] + 1 and after["note"] == "bigger tree"
    assert "bigger tree" in after["prompt"]
