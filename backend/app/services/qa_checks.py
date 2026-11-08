"""Programmatic QA (cheap, runs before vision QA). PLAN.md section 12."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .cleanup import to_gray

DEFAULTS = {
    "max_grey_ratio": 0.25,   # share of non-white pixels that are mid-grey
    "min_ink": 0.01,          # dark pixel fraction range
    "max_ink": 0.45,
    "edge_band": 0.01,        # outer band (fraction of side) that should be empty
    "max_edge_ink": 0.002,    # allowed dark fraction inside that band
    "max_open_ratio": 0.985,  # background region / all white pixels (approx. open outlines)
}


def analyze(data: bytes | Image.Image, limits: dict | None = None) -> dict:
    lim = {**DEFAULTS, **(limits or {})}
    gray = to_gray(data)
    # analyze at a bounded size for speed
    gray.thumbnail((768, 768))
    a = np.asarray(gray)
    h, w = a.shape
    non_white = a < 235
    dark = a < 110
    # grey pixels next to lines are anti-aliasing; grey pixels far from any
    # line are shading/fills.
    near_line = np.asarray(Image.fromarray(np.where(dark, 255, 0).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(5))) > 0
    grey = non_white & ~dark & ~near_line
    nw = int(non_white.sum())
    grey_ratio = float(grey.sum() / nw) if nw else 0.0
    ink = float(dark.sum() / a.size)

    band = max(1, int(min(h, w) * lim["edge_band"]))
    edge_mask = np.zeros_like(dark)
    edge_mask[:band, :] = True
    edge_mask[-band:, :] = True
    edge_mask[:, :band] = True
    edge_mask[:, -band:] = True
    edge_ink = float(dark[edge_mask].sum() / edge_mask.sum())

    open_ratio = _background_ratio(~dark)

    issues: list[str] = []
    if grey_ratio > lim["max_grey_ratio"]:
        issues.append(f"too much grey/shading ({grey_ratio:.0%} of drawn pixels)")
    if ink < lim["min_ink"]:
        issues.append(f"almost empty page (ink {ink:.1%})")
    if ink > lim["max_ink"]:
        issues.append(f"too much black ink (ink {ink:.0%}); avoid filled black areas")
    if edge_ink > lim["max_edge_ink"]:
        issues.append("subject touches the page edge; keep a margin")
    warnings: list[str] = []
    if open_ratio > lim["max_open_ratio"] and ink >= lim["min_ink"]:
        warnings.append("few closed regions detected (outlines may be open)")
    return {
        "pass": not issues,
        "issues": issues,
        "warnings": warnings,
        "metrics": {"grey_ratio": round(grey_ratio, 4), "ink": round(ink, 4), "edge_ink": round(edge_ink, 4),
                    "open_ratio": round(open_ratio, 4)},
    }


def _background_ratio(white: np.ndarray) -> float:
    """Fraction of white pixels connected to the page border (flood fill on a
    1px-padded copy, done in C by Pillow)."""
    total_white = int(white.sum())
    if total_white == 0:
        return 0.0
    h, w = white.shape
    padded = np.zeros((h + 2, w + 2), dtype=np.uint8)
    padded[1:-1, 1:-1] = np.where(white, 255, 0)
    padded[0, :] = padded[-1, :] = 255
    padded[:, 0] = padded[:, -1] = 255
    img = Image.fromarray(padded, "L").copy()  # copy: fromarray images may be read-only
    ImageDraw.floodfill(img, (0, 0), 128, thresh=0)
    filled = np.asarray(img)[1:-1, 1:-1] == 128
    return float(filled.sum() / total_white)
