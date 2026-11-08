"""Dot-to-dot pages: numbered points that trace a simple outline."""

from __future__ import annotations

import math

SHAPES: dict[str, list[tuple[float, float]]] = {
    "house": [(0.15, 0.95), (0.15, 0.45), (0.5, 0.1), (0.85, 0.45), (0.85, 0.95), (0.6, 0.95), (0.6, 0.7),
              (0.4, 0.7), (0.4, 0.95)],
    "fish": [(0.1, 0.5), (0.3, 0.3), (0.55, 0.25), (0.72, 0.35), (0.88, 0.2), (0.88, 0.8), (0.72, 0.65),
             (0.55, 0.75), (0.3, 0.7)],
    "tree": [(0.5, 0.05), (0.75, 0.35), (0.65, 0.35), (0.85, 0.6), (0.57, 0.6), (0.57, 0.95), (0.43, 0.95),
             (0.43, 0.6), (0.15, 0.6), (0.35, 0.35), (0.25, 0.35)],
    "cat": [(0.25, 0.95), (0.2, 0.45), (0.25, 0.1), (0.4, 0.3), (0.6, 0.3), (0.75, 0.1), (0.8, 0.45),
            (0.75, 0.95)],
    "balloon": [(0.5, 0.05), (0.75, 0.15), (0.85, 0.38), (0.75, 0.6), (0.55, 0.72), (0.5, 0.78), (0.45, 0.72),
                (0.25, 0.6), (0.15, 0.38), (0.25, 0.15)],
}


def _star(n: int = 5) -> list[tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        r = 0.48 if i % 2 == 0 else 0.2
        a = -math.pi / 2 + i * math.pi / n
        pts.append((0.5 + r * math.cos(a), 0.52 + r * math.sin(a)))
    return pts


def _heart(k: int = 16) -> list[tuple[float, float]]:
    pts = []
    for i in range(k):
        t = math.pi - 2 * math.pi * i / k
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((0.5 + x / 36, 0.45 - y / 36))
    return pts


def _circle(k: int = 14) -> list[tuple[float, float]]:
    return [(0.5 + 0.45 * math.cos(2 * math.pi * i / k - math.pi / 2), 0.5 + 0.45 * math.sin(2 * math.pi * i / k - math.pi / 2)) for i in range(k)]


SHAPES["star"] = _star()
SHAPES["heart"] = _heart()
SHAPES["circle"] = _circle()


def points_for(shape: str) -> list[tuple[float, float]]:
    return SHAPES.get(shape, SHAPES["star"])


def to_svg(shape: str, width: float, height: float, font_family: str = "DejaVu Sans") -> str:
    pts = points_for(shape)
    side = min(width, height)
    ox, oy = (width - side) / 2, (height - side) / 2
    r = side * 0.009
    fs = side * 0.035
    items = []
    for i, (x, y) in enumerate(pts, start=1):
        px, py = ox + x * side, oy + y * side
        items.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r:.1f}" fill="#000"/>')
        items.append(f'<text x="{px + r * 1.8:.1f}" y="{py - r * 1.8:.1f}" font-size="{fs:.1f}" '
                     f'font-family="{font_family}" fill="#000">{i}</text>')
    # star marker on the first dot (shape, not text)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" width="100%" height="100%">'
            + "".join(items) + "</svg>")
