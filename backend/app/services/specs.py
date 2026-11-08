"""Print specs: trim sizes, bleed, pixel sizes at 300 DPI."""

from __future__ import annotations

import re
from dataclasses import dataclass

DPI = 300
BLEED_IN = 0.125
SAFE_MARGIN_IN = 0.5
MM_PER_IN = 25.4

TRIM_SIZES: dict[str, tuple[float, float]] = {
    "A4": (210 / MM_PER_IN, 297 / MM_PER_IN),
    "A5": (148 / MM_PER_IN, 210 / MM_PER_IN),
    "8.5x11in": (8.5, 11.0),
    "8x10in": (8.0, 10.0),
    "6x9in": (6.0, 9.0),
}
_CUSTOM = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(in|mm)\s*$", re.I)


class SpecError(ValueError):
    pass


def trim_inches(trim: str) -> tuple[float, float]:
    if trim in TRIM_SIZES:
        return TRIM_SIZES[trim]
    m = _CUSTOM.match(trim or "")
    if not m:
        raise SpecError(f"unknown trim size '{trim}' (use one of {list(TRIM_SIZES)} or e.g. '7x10in' / '200x250mm')")
    w, h, unit = float(m.group(1)), float(m.group(2)), m.group(3).lower()
    if unit == "mm":
        w, h = w / MM_PER_IN, h / MM_PER_IN
    if not (2 <= w <= 20 and 2 <= h <= 20):
        raise SpecError("custom trim size must be between 2 and 20 inches per side")
    return w, h


@dataclass(frozen=True)
class PageSpec:
    trim: str
    bleed: bool
    width_in: float
    height_in: float
    dpi: int = DPI

    @property
    def bleed_in(self) -> float:
        return BLEED_IN if self.bleed else 0.0

    @property
    def page_width_in(self) -> float:
        return self.width_in + 2 * self.bleed_in

    @property
    def page_height_in(self) -> float:
        return self.height_in + 2 * self.bleed_in

    @property
    def pixel_size(self) -> tuple[int, int]:
        return round(self.page_width_in * self.dpi), round(self.page_height_in * self.dpi)

    @property
    def points(self) -> tuple[float, float]:
        return self.page_width_in * 72, self.page_height_in * 72

    @property
    def safe_margin_px(self) -> int:
        return round((SAFE_MARGIN_IN + self.bleed_in) * self.dpi)

    def as_dict(self) -> dict:
        w, h = self.pixel_size
        return {
            "trim": self.trim, "bleed": self.bleed, "dpi": self.dpi,
            "trim_in": [round(self.width_in, 4), round(self.height_in, 4)],
            "page_in": [round(self.page_width_in, 4), round(self.page_height_in, 4)],
            "pixels": [w, h], "points": [round(self.points[0], 2), round(self.points[1], 2)],
            "safe_margin_in": SAFE_MARGIN_IN, "bleed_in": self.bleed_in,
        }


def page_spec(trim: str, bleed: bool) -> PageSpec:
    w, h = trim_inches(trim)
    return PageSpec(trim, bleed, w, h)
