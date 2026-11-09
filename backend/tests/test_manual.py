"""Manual mode (ChatGPT tasks), offline: a helper answers every task like the
user would (text: the mock's canned JSON, images: mock line art)."""

import json

import pytest

from .conftest import needs_api, needs_weasy, run_jobs
from .helpers import new_book, ready_book, themed_book, wait_ok

pytestmark = needs_api


@pytest.fixture
def manual_on(monkeypatch):
    monkeypatch.setenv("MANUAL_MODE", "1")


# ------------------------------------------------------------------ helpers


def pending(client, bid):
    return client.get(f"/api/books/{bid}/manual").json()["pending"]


def task_row(task_id):
    from app.db import SessionLocal
    from app.models import ManualTask

    with SessionLocal() as s:
        t = s.get(ManualTask, task_id)
        return t.task, dict(t.meta or {})


def canned_answer(task_id) -> dict:
    from app.providers.mock import _canned

    task, meta = task_row(task_id)
    return _canned(task, meta.get("vars") or {})


def answer_text(client, t, data=None):
    data = canned_answer(t["id"]) if data is None else data
    r = client.post(f"/api/manual/{t['id']}/text", json={"text": "Sure! Here it is:\n```json\n" + json.dumps(data) + "\n```"})
    assert r.status_code == 200, r.text
    return r.json()


def mock_png(t) -> bytes:
    from app.providers.mock import MockImageProvider

    size = tuple(t.get("size") or (1024, 1024))
    return MockImageProvider().generate(t["prompt"], size, seed=t["id"])


def answer_image(client, t):
    r = client.post(f"/api/manual/{t['id']}/image", files={"file": ("chatgpt.png", mock_png(t), "image/png")})
    assert r.status_code == 200, r.text
    return r.json()


def answer_all(client, bid, skip=lambda t: False) -> int:
    n = 0
    for t in pending(client, bid):
        if t["kind"] == "image" and skip(t):
            r = client.post(f"/api/manual/{t['id']}/skip")
            assert r.status_code == 200, r.text
        elif t["kind"] == "text":
            answer_text(client, t)
        else:
            answer_image(client, t)
        n += 1
    return n


def finish(client, job, skip=lambda t: False, rounds=40) -> dict:
    """Run the job, answer its ChatGPT tasks whenever it waits, until done."""
    for _ in range(rounds):
        run_jobs()
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] == "waiting":
            assert answer_all(client, j["book_id"], skip) > 0, "waiting job without open tasks"
            continue
        assert j["status"] == "done", j
        return j
    raise AssertionError("job did not finish")


def char(client, bid, cid):
    return next(c for c in client.get(f"/api/books/{bid}/characters").json()["characters"] if c["id"] == cid)


def count_tasks(bid) -> int:
    from app.db import SessionLocal
    from app.models import ManualTask

    with SessionLocal() as s:
        return s.query(ManualTask).filter(ManualTask.book_id == bid).count()


# -------------------------------------------------------------------- tests


def test_mode_switch_setting_env_and_auto(client, monkeypatch):
    assert client.get("/api/settings").json()["manual"]["active"] is False  # conftest: MANUAL_MODE=0
    r = client.put("/api/settings", json={"manual_mode": True})
    assert r.status_code == 200 and r.json()["manual"]["active"] is True
    assert client.get("/api/health").json()["manual_mode"] is True
    client.put("/api/settings", json={"manual_mode": None})
    assert client.get("/api/settings").json()["manual"]["active"] is False
    monkeypatch.delenv("MANUAL_MODE")  # auto: no API key + mock images -> manual
    assert client.get("/api/settings").json()["manual"]["active"] is True
    assert client.put("/api/settings", json={"manual_mode": "yes"}).status_code == 422


@needs_weasy
def test_full_manual_book_end_to_end(client, manual_on):
    from app.services import storage

    b = new_book(client)
    bid = b["id"]
    assert client.get(f"/api/books/{bid}/manual").json()["manual_mode"] is True

    # 1. analysis: one text task, the job waits for it
    job = client.post(f"/api/books/{bid}/source", data={"text": "A cozy coloring book with cute bakery animals for ages 4-8."}).json()["job"]
    run_jobs()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "waiting"
    [t] = pending(client, bid)
    assert t["kind"] == "text" and t["task"] == "analyze_source" and "ONE JSON object" in t["prompt"]
    finish(client, job)
    assert client.get(f"/api/books/{bid}").json()["recipe"]["mood"]

    # 2. themes and formats: one text task each
    finish(client, client.post(f"/api/books/{bid}/themes/propose").json())
    themes = client.get(f"/api/books/{bid}/themes").json()
    assert len(themes) == 3
    client.post(f"/api/books/{bid}/themes/choose", json={"theme_id": themes[0]["id"]})
    finish(client, client.post(f"/api/books/{bid}/formats/propose").json())
    fmts = client.get(f"/api/books/{bid}/formats").json()
    assert client.post(f"/api/books/{bid}/formats/{fmts[1]['id']}/choose").status_code == 200

    # 3. characters: brief (text), candidates (4 images, one skipped)
    finish(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": 1}).json())
    cid = client.get(f"/api/books/{bid}/characters").json()["characters"][0]["id"]
    job = client.post(f"/api/books/{bid}/characters/{cid}/candidates").json()
    run_jobs()
    cand_tasks = pending(client, bid)
    assert len(cand_tasks) == 4 and all(x["kind"] == "image" and x["skippable"] for x in cand_tasks)
    [group] = client.get(f"/api/books/{bid}/manual").json()["groups"]
    assert len(group["tasks"]) == 4 and group["job_type"] == "character_candidates"
    assert "ONE AT A TIME" in group["all_prompts"] and "### Image 4 of 4" in group["all_prompts"]
    finish(client, job, skip=lambda x: x["label"] == "4")
    cands = [a for a in char(client, bid, cid)["assets"] if a["kind"] == "candidate"]
    assert len(cands) == 3  # the skipped candidate was not created
    assert client.post(f"/api/books/{bid}/characters/{cid}/select/{cands[0]['id']}").status_code == 200

    # lock and edit: template prompt, selected image as reference, no LLM
    job = client.post(f"/api/books/{bid}/characters/{cid}/edit", json={"instruction": "shorter ears"}).json()
    run_jobs()
    [t] = pending(client, bid)
    assert t["task"] == "character_edit" and "change ONLY this: shorter ears" in t["prompt"]
    assert t["refs"] and client.get(t["refs"][0]["url"]).status_code == 200
    finish(client, job)
    sel = [a for a in char(client, bid, cid)["assets"] if a["kind"] == "candidate" and a["selected"]]
    assert len(sel) == 1 and sel[0]["meta"]["instruction"] == "shorter ears"

    # sheet: ONE combined image
    job = client.post(f"/api/books/{bid}/characters/{cid}/sheet").json()
    run_jobs()
    assert len(pending(client, bid)) == 1
    finish(client, job)
    sheet = [a for a in char(client, bid, cid)["assets"] if a["kind"] in ("sheet", "expression")]
    assert len(sheet) == 1 and sheet[0]["meta"]["view"] == "combined"

    # consistency: 3 test scenes, judged by the user
    finish(client, client.post(f"/api/books/{bid}/characters/{cid}/consistency").json())
    cons = char(client, bid, cid)["consistency"]
    assert cons["manual"] and cons["pass"] is False and len(cons["results"]) == 3
    assert all(r["pass"] is None for r in cons["results"])
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).status_code == 409
    for r in cons["results"]:
        res = client.post(f"/api/books/{bid}/characters/{cid}/consistency/verdict", json={"asset_id": r["asset_id"], "pass": True})
        assert res.status_code == 200, res.text
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).json()["status"] == "approved"

    # sample page (1 image), ChatGPT setup card
    finish(client, client.post(f"/api/books/{bid}/sample").json())
    assert client.post(f"/api/books/{bid}/sample/approve").status_code == 200
    setup = client.get(f"/api/books/{bid}/chatgpt-setup").json()
    assert "HOW WE WORK" in setup["instructions"] and themes[0]["title"] in setup["instructions"]
    kinds = {r["kind"] for r in setup["references"]}
    assert {"style", "sheet"} <= kinds and all(client.get(r["url"]).status_code == 200 for r in setup["references"])

    # 4. plan (1 text task, page count enforced) and generation in batches of 5
    client.patch(f"/api/books/{bid}", json={"page_count": 12})
    finish(client, client.post(f"/api/books/{bid}/plan").json())
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert len(pages) == 12
    image_pages = [p for p in pages if p["is_image"]]
    assert len(image_pages) > 5
    client.put("/api/settings", json={"batch_size": 5})
    job = client.post(f"/api/books/{bid}/generate").json()
    run_jobs()
    first = pending(client, bid)
    assert len(first) == 5 and [x["label"] for x in first] == [str(p["index"]) for p in image_pages[:5]]
    assert "NO text" in first[0]["prompt"] and first[0]["refs"]
    assert all(p["status"] == "generated" for p in client.get(f"/api/books/{bid}/pages").json() if not p["is_image"])
    finish(client, job)
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert all(p["status"] == "generated" for p in pages), [(p["index"], p["status"], p["qa"]) for p in pages]
    assert all(p["image_url"] for p in pages)
    assert max(p["batch_no"] for p in pages if p["is_image"]) == 2
    assert client.get(f"/api/books/{bid}").json()["status"] == "review"

    # cover art is optional: skipping it is fine
    j = finish(client, client.post(f"/api/books/{bid}/cover/art").json(), skip=lambda x: True)
    assert j["result"].get("skipped") is True

    # 5. review + export
    client.post(f"/api/books/{bid}/review/approve-all")
    wait_ok(client, client.post(f"/api/books/{bid}/export", json={}).json())
    files = client.get(f"/api/books/{bid}/export/files").json()["files"]
    assert {"interior.pdf", "cover.pdf", "book-settings.json"} <= set(files)
    assert (storage.export_dir(bid) / "interior.pdf").is_file()
    assert client.get(f"/api/books/{bid}/manual").json()["pending"] == []


def test_waiting_job_resumes_without_duplicate_tasks(client, manual_on):
    from app.db import SessionLocal
    from app.jobs import runner
    from app.models import Job

    bid = new_book(client)["id"]
    job = client.post(f"/api/books/{bid}/source", data={"text": "Bold simple animals for toddlers."}).json()["job"]
    run_jobs()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "waiting"
    assert "Waiting for ChatGPT" in client.get(f"/api/jobs/{job['id']}").json()["message"]
    assert count_tasks(bid) == 1
    # waiting jobs are not picked up by the worker, and count as active
    assert runner.claim_next() is None
    with SessionLocal() as s:
        assert runner.active_job(s, bid, "analyze_source").id == job["id"]
        # a forced re-run (e.g. after a restart) does not ask twice
        s.get(Job, job["id"]).status = "queued"
        s.commit()
    run_jobs()
    assert count_tasks(bid) == 1 and len(pending(client, bid)) == 1
    answer_all(client, bid)
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"  # auto-resumed
    run_jobs()
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "done"
    assert count_tasks(bid) == 1

    # a cancelled waiting job hides its tasks
    job = client.post(f"/api/books/{bid}/themes/propose").json()
    run_jobs()
    assert len(pending(client, bid)) == 1
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["status"] == "cancelled"
    assert pending(client, bid) == []
    # retrying it shows the same task again (same job, same key)
    client.post(f"/api/jobs/{job['id']}/retry")
    run_jobs()
    assert len(pending(client, bid)) == 1 and count_tasks(bid) == 2


def test_invalid_answers_get_errors_and_fix_prompt(client, manual_on):
    bid = new_book(client)["id"]
    finish(client, client.post(f"/api/books/{bid}/source", data={"text": "Cute farm animals, thick lines."}).json()["job"])
    job = client.post(f"/api/books/{bid}/themes/propose").json()
    run_jobs()
    [t] = pending(client, bid)
    r = client.post(f"/api/manual/{t['id']}/text", json={"text": "Sorry, here are some ideas: a farm, a zoo."})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["errors"] and "JSON" in detail["errors"][0]
    assert "could not be used" in detail["fix_prompt"] and "ONE JSON object" in detail["fix_prompt"]
    r = client.post(f"/api/manual/{t['id']}/text", json={"text": '{"themes": []}'})
    assert r.status_code == 422 and any("themes" in e for e in r.json()["detail"]["errors"])
    r = client.post(f"/api/manual/{t['id']}/text", json={"text": '{"themes": [{"title": "Farm"}]}'})
    assert r.status_code == 422 and any("description" in e for e in r.json()["detail"]["errors"])
    assert client.post(f"/api/manual/{t['id']}/image", files={"file": ("x.png", b"x", "image/png")}).status_code == 409
    answer_text(client, t)
    assert client.post(f"/api/manual/{t['id']}/text", json={"text": "{}"}).status_code == 409  # already answered
    finish(client, job)
    themes = client.get(f"/api/books/{bid}/themes").json()
    client.post(f"/api/books/{bid}/themes/choose", json={"theme_id": themes[0]["id"]})
    finish(client, client.post(f"/api/books/{bid}/formats/propose").json())
    fmt = client.get(f"/api/books/{bid}/formats").json()[0]
    client.post(f"/api/books/{bid}/formats/{fmt['id']}/choose")

    # wrong page count is rejected with the exact number in the fix prompt
    client.patch(f"/api/books/{bid}", json={"page_count": 10})
    job = client.post(f"/api/books/{bid}/plan").json()
    run_jobs()
    [t] = pending(client, bid)
    assert t["expected_count"] == 7
    good = canned_answer(t["id"])
    bad = {"pages": good["pages"][:-1]}
    r = client.post(f"/api/manual/{t['id']}/text", json={"text": json.dumps(bad)})
    assert r.status_code == 422
    assert any("exactly 7" in e for e in r.json()["detail"]["errors"]) and "exactly 7 items" in r.json()["detail"]["fix_prompt"]
    answer_text(client, t, good)
    finish(client, job)
    assert len(client.get(f"/api/books/{bid}/pages").json()) == 10


def test_skip_rules_for_candidates(client, monkeypatch):
    b = themed_book(client)  # API mode up to here
    bid = b["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": 1}).json())
    cid = client.get(f"/api/books/{bid}/characters").json()["characters"][0]["id"]
    monkeypatch.setenv("MANUAL_MODE", "1")
    job = client.post(f"/api/books/{bid}/characters/{cid}/candidates").json()
    run_jobs()
    tasks = pending(client, bid)
    for t in tasks[:3]:
        assert client.post(f"/api/manual/{t['id']}/skip").status_code == 200
    assert client.post(f"/api/manual/{tasks[3]['id']}/skip").status_code == 409  # at least one image is needed
    assert client.post(f"/api/manual/{tasks[0]['id']}/skip").status_code == 409  # already skipped
    answer_image(client, tasks[3])
    finish(client, job)
    assert len([a for a in char(client, bid, cid)["assets"] if a["kind"] == "candidate"]) == 1


def test_consistency_verdicts_gate_approval(client, monkeypatch):
    b = themed_book(client)
    bid = b["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/characters/briefs", json={"count": 1}).json())
    cid = client.get(f"/api/books/{bid}/characters").json()["characters"][0]["id"]
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/candidates").json())
    cand = [a for a in char(client, bid, cid)["assets"] if a["kind"] == "candidate"][0]
    client.post(f"/api/books/{bid}/characters/{cid}/select/{cand['id']}")
    wait_ok(client, client.post(f"/api/books/{bid}/characters/{cid}/sheet").json())
    monkeypatch.setenv("MANUAL_MODE", "1")
    # one scene skipped in ChatGPT: only two results to judge
    finish(client, client.post(f"/api/books/{bid}/characters/{cid}/consistency").json(), skip=lambda t: t["label"] == "3")
    cons = char(client, bid, cid)["consistency"]
    assert len(cons["results"]) == 2 and cons["pass"] is False
    a, b2 = (r["asset_id"] for r in cons["results"])
    url = f"/api/books/{bid}/characters/{cid}/consistency/verdict"
    client.post(url, json={"asset_id": a, "pass": True})
    c = client.post(url, json={"asset_id": b2, "pass": False, "issues": ["scarf missing"]}).json()
    assert c["consistency"]["pass"] is False and c["consistency"]["results"][1]["issues"] == ["scarf missing"]
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).status_code == 409
    client.post(url, json={"asset_id": b2, "pass": True})
    assert client.post(f"/api/books/{bid}/characters/{cid}/approve", json={}).json()["status"] == "approved"
    # changing a verdict to fail withdraws the approval; override still works
    c = client.post(url, json={"asset_id": a, "pass": False}).json()
    assert c["status"] == "draft"
    r = client.post(f"/api/books/{bid}/characters/{cid}/approve", json={"override": True})
    assert r.status_code == 200 and r.json()["consistency"]["override"] is True
    assert client.post(url, json={"asset_id": 999999, "pass": True}).status_code == 404


@needs_weasy
def test_bulk_upload_matching_skip_and_redo(client, monkeypatch):
    b = ready_book(client, page_count=14)  # API mode up to the page plan
    bid = b["id"]
    monkeypatch.setenv("MANUAL_MODE", "1")
    client.put("/api/settings", json={"batch_size": 10})
    job = client.post(f"/api/books/{bid}/generate").json()
    run_jobs()
    tasks = pending(client, bid)
    assert 3 <= len(tasks) <= 10
    labels = [t["label"] for t in tasks]
    # named files in reverse order, plus one ChatGPT default file name (its numbers must be ignored)
    named = list(reversed(tasks[1:]))
    files = [("files", (f"page_{t['label']}.png", mock_png(t), "image/png")) for t in named]
    files.append(("files", ("ChatGPT Image Nov 9, 2026, 10_15_32 AM.png", mock_png(tasks[0]), "image/png")))
    files.append(("files", ("extra.png", mock_png(tasks[0]), "image/png")))
    r = client.post(f"/api/books/{bid}/manual/images", files=files)
    assert r.status_code == 200, r.text
    res = r.json()
    by_file = {m["file"]: m["label"] for m in res["matched"]}
    for t in named:
        assert by_file[f"page_{t['label']}.png"] == t["label"]
    assert by_file["ChatGPT Image Nov 9, 2026, 10_15_32 AM.png"] == labels[0]
    assert res["unmatched"] == ["extra.png"] and res["errors"] == []
    assert client.get(f"/api/jobs/{job['id']}").json()["status"] == "queued"
    finish(client, job)
    pages = client.get(f"/api/books/{bid}/pages").json()
    assert all(p["status"] == "generated" for p in pages)

    # skipped page -> failed; redo of a rejected page asks again with the note appended
    target = next(p for p in pages if p["is_image"])
    client.post(f"/api/books/{bid}/pages/{target['id']}/review", json={"status": "rejected"})
    r = client.post(f"/api/books/{bid}/review/redo", json={"note": "bigger tree"}).json()
    run_jobs()
    [t] = pending(client, bid)
    assert t["label"] == str(target["index"]) and "bigger tree" in t["prompt"] and "user rejected" in t["prompt"]
    finish(client, r["job"], skip=lambda x: True)
    p = client.get(f"/api/books/{bid}/pages/{target['id']}").json()
    assert p["status"] == "failed" and p["qa"]["skipped"] is True
    # asking again creates a new task (the attempt changed), it is not the skipped one
    r = client.post(f"/api/books/{bid}/pages/{target['id']}/regenerate", json={}).json()
    run_jobs()
    [t2] = pending(client, bid)
    assert t2["id"] != t["id"]
    finish(client, r)
    assert client.get(f"/api/books/{bid}/pages/{target['id']}").json()["status"] == "generated"


def test_number_in_filename():
    from app.services.manual import number_in_filename

    assert number_in_filename("page_12.png") == "12"
    assert number_in_filename("Page 7.JPG") == "7"
    assert number_in_filename("p03.webp") == "3"
    assert number_in_filename("12.png") == "12"
    assert number_in_filename("ChatGPT Image Nov 9, 2026, 10_15_32 AM.png") is None
    assert number_in_filename("dodo.png") is None


def test_text_prompt_and_schema_are_compact():
    from app.schemas import ThemesOut
    from app.services.manual import compact_schema, text_prompt

    s = compact_schema(ThemesOut.model_json_schema())
    assert '"title":{' in s  # the property named "title" is kept
    assert '"title":"ThemesOut"' not in s  # schema titles are dropped
    p = text_prompt("Do it.", ThemesOut.model_json_schema(), refs_count=2)
    assert p.startswith("Do it.") and "attached 2 picture" in p and "ONE JSON object" in p
