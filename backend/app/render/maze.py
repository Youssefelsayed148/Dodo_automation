"""Solvable rectangular mazes (recursive backtracker) rendered as SVG."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

N, S, E, W = 1, 2, 4, 8
DX = {E: 1, W: -1, N: 0, S: 0}
DY = {E: 0, W: 0, N: -1, S: 1}
OPP = {E: W, W: E, N: S, S: N}

DIFFICULTY_CELLS = {"easy": 8, "medium": 13, "hard": 20}


@dataclass
class Maze:
    cols: int
    rows: int
    cells: list[list[int]] = field(default_factory=list)  # bitmask of OPEN directions

    @property
    def start(self) -> tuple[int, int]:
        return (0, 0)

    @property
    def end(self) -> tuple[int, int]:
        return (self.cols - 1, self.rows - 1)

    def neighbors(self, x: int, y: int):
        for d in (N, S, E, W):
            if self.cells[y][x] & d:
                yield x + DX[d], y + DY[d]

    def solve(self) -> list[tuple[int, int]] | None:
        prev: dict[tuple[int, int], tuple[int, int] | None] = {self.start: None}
        q = deque([self.start])
        while q:
            cur = q.popleft()
            if cur == self.end:
                path = []
                node: tuple[int, int] | None = cur
                while node is not None:
                    path.append(node)
                    node = prev[node]
                return path[::-1]
            for nb in self.neighbors(*cur):
                if nb not in prev:
                    prev[nb] = cur
                    q.append(nb)
        return None


def generate(cols: int, rows: int, seed: int | None = None) -> Maze:
    rng = random.Random(seed)
    cells = [[0] * cols for _ in range(rows)]
    visited = [[False] * cols for _ in range(rows)]
    stack = [(0, 0)]
    visited[0][0] = True
    while stack:
        x, y = stack[-1]
        dirs = [d for d in (N, S, E, W)
                if 0 <= x + DX[d] < cols and 0 <= y + DY[d] < rows and not visited[y + DY[d]][x + DX[d]]]
        if not dirs:
            stack.pop()
            continue
        d = rng.choice(dirs)
        nx, ny = x + DX[d], y + DY[d]
        cells[y][x] |= d
        cells[ny][nx] |= OPP[d]
        visited[ny][nx] = True
        stack.append((nx, ny))
    return Maze(cols, rows, cells)


def for_page(difficulty: str, aspect: float, seed: int | None = None) -> Maze:
    """aspect = width / height of the drawing area."""
    base = DIFFICULTY_CELLS.get(difficulty, DIFFICULTY_CELLS["easy"])
    cols = base
    rows = max(4, round(base / aspect)) if aspect > 0 else base
    return generate(cols, rows, seed)


def to_svg(m: Maze, width: float, height: float, stroke: float = 4.0, show_solution: bool = False) -> str:
    cw, ch = width / m.cols, height / m.rows
    lines: list[str] = []

    def seg(x1, y1, x2, y2):
        lines.append(f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}"/>')

    for y in range(m.rows):
        for x in range(m.cols):
            c = m.cells[y][x]
            px, py = x * cw, y * ch
            if not c & N and not (x, y) == m.start:
                seg(px, py, px + cw, py)
            if not c & W:
                seg(px, py, px, py + ch)
            if y == m.rows - 1 and not (x, y) == m.end:
                seg(px, py + ch, px + cw, py + ch)
            if x == m.cols - 1:
                seg(px + cw, py, px + cw, py + ch)
    sol = ""
    if show_solution:
        path = m.solve() or []
        pts = " ".join(f"{(x + .5) * cw:.1f},{(y + .5) * ch:.1f}" for x, y in path)
        sol = f'<polyline points="{pts}" fill="none" stroke="#000" stroke-dasharray="6 6" stroke-width="{stroke / 2}"/>'
    # start / end arrows (shapes, no text)
    a = min(cw, ch) * 0.35
    sx, ex, ey = cw / 2, (m.cols - .5) * cw, height
    arrows = (f'<polygon points="{sx - a:.1f},{-a * 1.6:.1f} {sx + a:.1f},{-a * 1.6:.1f} {sx:.1f},{-a * 0.3:.1f}"/>'
              f'<polygon points="{ex - a:.1f},{ey + a * 0.3:.1f} {ex + a:.1f},{ey + a * 0.3:.1f} {ex:.1f},{ey + a * 1.6:.1f}"/>')
    pad = a * 2
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-stroke} {-pad} {width + 2 * stroke} {height + 2 * pad}" '
            f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">'
            f'<g stroke="#000" stroke-width="{stroke}" stroke-linecap="square">{"".join(lines)}</g>'
            f'<g fill="#000">{arrows}</g>{sol}</svg>')
