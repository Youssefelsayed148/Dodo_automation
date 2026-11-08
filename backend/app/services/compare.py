"""Image model comparison harness (PLAN.md sections 9 and 20).

Same theme, character sheet and 10 page prompts through each configured
provider. Outputs go to data/compare/<run>/<provider>/NN.png plus
results.json (time, estimated cost, programmatic QA, manual 1-5 scores).
The harness never picks a winner.

CLI:  python -m app.services.compare --providers mock,openai,gemini [--theme "..."] [--sheet path.png]
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..providers.base import UsageRecord, add_usage_sink, remove_usage_sink
from ..providers.registry import available_image_providers, get_image_provider
from . import qa_checks
from .prompts import NO_TEXT_RULE

DEFAULT_THEME = "Little garden friends: a small bear cub with a patched left ear and a bunny in a striped scarf"
DEFAULT_SCENES = [
    "the bear cub waters flowers with a small watering can",
    "the bunny reads a picture book under a tree",
    "both friends have a picnic on a blanket",
    "the bear cub flies a kite on a hill",
    "the bunny plants a seed in a pot",
    "both friends build a sandcastle at a lake",
    "the bear cub bakes round cookies in a kitchen",
    "the bunny paints a wooden fence",
    "both friends watch the stars from a rooftop",
    "single portrait of the bear cub smiling, centered",
]
STYLE = ("Black and white coloring-book line art, bold clean black outlines, pure white background, no shading, "
         "no grey, closed shapes, simple background, subject fully inside the page with a margin. " + NO_TEXT_RULE)
SCORE_FIELDS = ("clean_outlines", "matches_sheet")


def page_prompts(theme: str, scenes: list[str] | None = None) -> list[str]:
    return [f"{theme}. Scene: {s}. {STYLE}" for s in (scenes or default_scenes())[:10]]


def default_scenes() -> list[str]:
    return list(DEFAULT_SCENES)


def run_compare(providers: list[str], theme: str = DEFAULT_THEME, sheet: bytes | None = None,
                scenes: list[str] | None = None, out_root: Path | None = None,
                progress=lambda p, m=None: None) -> dict[str, Any]:
    out_root = out_root or get_settings().compare_dir
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = out_root / run_id
    n = 1
    while run_dir.exists():
        run_dir = out_root / f"{run_id}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    prompts = page_prompts(theme, scenes)
    if sheet:
        (run_dir / "sheet.png").write_bytes(sheet)
    captured: list[UsageRecord] = []
    sink = captured.append
    add_usage_sink(sink)
    results: dict[str, Any] = {"run": run_dir.name, "theme": theme, "prompts": prompts, "providers": {},
                               "created": datetime.now(UTC).isoformat()}
    total = len(providers) * len(prompts)
    k = 0
    try:
        for name in providers:
            entry: dict[str, Any] = {"outputs": [], "errors": 0}
            try:
                provider = get_image_provider(name)
                entry["model"] = provider.model
            except Exception as e:  # noqa: BLE001
                entry["error"] = str(e)
                results["providers"][name] = entry
                k += len(prompts)
                continue
            pdir = run_dir / name
            pdir.mkdir(exist_ok=True)
            for i, prompt in enumerate(prompts):
                before = len(captured)
                t0 = time.perf_counter()
                rec: dict[str, Any] = {"index": i + 1, "prompt": prompt, "scores": {f: None for f in SCORE_FIELDS}}
                try:
                    data = provider.generate(prompt, (2550, 3300), reference_images=[sheet] if sheet else [], seed=i)
                    rec["seconds"] = round(time.perf_counter() - t0, 2)
                    path = pdir / f"{i + 1:02d}.png"
                    path.write_bytes(data)
                    rec["file"] = str(path.relative_to(run_dir))
                    qa = qa_checks.analyze(data)
                    rec["qa"] = {"pass": qa["pass"], "issues": qa["issues"], **qa["metrics"]}
                except Exception as e:  # noqa: BLE001
                    rec["seconds"] = round(time.perf_counter() - t0, 2)
                    rec["error"] = str(e)
                    entry["errors"] += 1
                rec["cost_usd"] = round(sum(r.est_cost_usd for r in captured[before:]), 4)
                entry["outputs"].append(rec)
                k += 1
                progress(k / total, f"{name} {i + 1}/{len(prompts)}")
            results["providers"][name] = entry
    finally:
        remove_usage_sink(sink)
    results["summary"] = summarize(results)
    (run_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def summarize(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, entry in results.get("providers", {}).items():
        outs = entry.get("outputs", [])
        ok = [o for o in outs if "error" not in o]
        def avg(vals):
            vals = [v for v in vals if v is not None]
            return round(sum(vals) / len(vals), 2) if vals else None
        rows.append({
            "provider": name, "model": entry.get("model", ""), "images": len(ok), "errors": entry.get("errors", 0) + (len(outs) == 0 and bool(entry.get("error"))),
            "avg_seconds": avg([o.get("seconds") for o in ok]),
            "total_cost_usd": round(sum(o.get("cost_usd", 0) for o in outs), 4),
            "qa_redo_rate": round(sum(1 for o in ok if not o["qa"]["pass"]) / len(ok), 2) if ok else None,
            "avg_clean_outlines": avg([o["scores"].get("clean_outlines") for o in ok]),
            "avg_matches_sheet": avg([o["scores"].get("matches_sheet") for o in ok]),
        })
    return rows


def format_table(rows: list[dict[str, Any]]) -> str:
    cols = ["provider", "model", "images", "errors", "avg_seconds", "total_cost_usd", "qa_redo_rate",
            "avg_clean_outlines", "avg_matches_sheet"]
    widths = {c: max(len(c), *(len(str(r.get(c))) for r in rows)) if rows else len(c) for c in cols}
    line = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = "\n".join(" | ".join(str(r.get(c)).ljust(widths[c]) for c in cols) for r in rows)
    return f"{line}\n{sep}\n{body}"


def list_runs(root: Path | None = None) -> list[dict[str, Any]]:
    root = root or get_settings().compare_dir
    out = []
    for d in sorted(root.glob("*"), reverse=True):
        f = d / "results.json"
        if f.is_file():
            data = json.loads(f.read_text())
            out.append({"run": d.name, "created": data.get("created"), "providers": list(data.get("providers", {})),
                        "summary": data.get("summary", [])})
    return out


def load_run(run: str, root: Path | None = None) -> dict[str, Any]:
    root = root or get_settings().compare_dir
    d = (root / run).resolve()
    if root.resolve() not in d.parents or not (d / "results.json").is_file():
        raise KeyError(run)
    return json.loads((d / "results.json").read_text())


def save_scores(run: str, provider: str, index: int, scores: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    root = root or get_settings().compare_dir
    data = load_run(run, root)
    entry = data["providers"].get(provider)
    if entry is None:
        raise KeyError(provider)
    for o in entry["outputs"]:
        if o["index"] == index:
            for k, v in scores.items():
                if k not in SCORE_FIELDS:
                    raise ValueError(f"unknown score '{k}'")
                if v is not None and not (1 <= int(v) <= 5):
                    raise ValueError("scores must be 1-5")
                o["scores"][k] = None if v is None else int(v)
    data["summary"] = summarize(data)
    (root / run / "results.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compare image providers on the same prompts")
    ap.add_argument("--providers", default="", help="comma list; default: all configured")
    ap.add_argument("--theme", default=DEFAULT_THEME)
    ap.add_argument("--sheet", default="", help="path to an approved character sheet image")
    ap.add_argument("--scenes", default="", help="optional file with one scene per line (10 used)")
    args = ap.parse_args(argv)
    providers = [p.strip() for p in args.providers.split(",") if p.strip()] or \
        [p["name"] for p in available_image_providers() if p["configured"]]
    sheet = Path(args.sheet).read_bytes() if args.sheet else None
    scenes = [ln.strip() for ln in Path(args.scenes).read_text().splitlines() if ln.strip()] if args.scenes else None
    res = run_compare(providers, args.theme, sheet, scenes,
                      progress=lambda p, m=None: print(f"[{p:5.0%}] {m}", flush=True))
    print(f"\nRun saved to {get_settings().compare_dir / res['run']}\n")
    print(format_table(res["summary"]))
    print("\nOpen Settings > Compare in the app to score outputs (1-5). No winner is picked automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
