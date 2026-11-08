import json

from app.services import compare


def test_compare_harness_on_mock(tmp_path):
    res = compare.run_compare(["mock", "openai"], out_root=tmp_path)  # openai has no key -> recorded error
    run_dir = tmp_path / res["run"]
    data = json.loads((run_dir / "results.json").read_text())
    outs = data["providers"]["mock"]["outputs"]
    assert len(outs) == 10
    assert all((run_dir / o["file"]).is_file() for o in outs)
    assert all({"seconds", "cost_usd", "qa", "scores"} <= set(o) for o in outs)
    assert "error" in data["providers"]["openai"]
    rows = {r["provider"]: r for r in data["summary"]}
    assert rows["mock"]["images"] == 10
    table = compare.format_table(data["summary"])
    assert "provider" in table and "mock" in table


def test_scores_saved_and_summarized(tmp_path):
    res = compare.run_compare(["mock"], out_root=tmp_path)
    data = compare.save_scores(res["run"], "mock", 1, {"clean_outlines": 4, "matches_sheet": 2}, root=tmp_path)
    row = data["summary"][0]
    assert row["avg_clean_outlines"] == 4 and row["avg_matches_sheet"] == 2
    assert compare.list_runs(tmp_path)[0]["run"] == res["run"]
