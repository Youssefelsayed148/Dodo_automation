"""Word search grids with answer key. Supports English and Arabic (RTL)."""

from __future__ import annotations

import random
import unicodedata
from dataclasses import dataclass, field
from html import escape

EN_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
AR_ALPHABET = "ابتثجحخدذرزسشصضطظعغفقكلمنهوي"

# (dx, dy). English reads left->right, Arabic right->left.
DIRS_EASY_EN = [(1, 0), (0, 1)]
DIRS_EASY_AR = [(-1, 0), (0, 1)]
DIRS_HARD_EN = DIRS_EASY_EN + [(1, 1), (1, -1)]
DIRS_HARD_AR = DIRS_EASY_AR + [(-1, 1), (-1, -1)]


@dataclass
class Placement:
    word: str
    x: int
    y: int
    dx: int
    dy: int

    def cells(self) -> list[tuple[int, int]]:
        return [(self.x + i * self.dx, self.y + i * self.dy) for i in range(len(self.word))]


@dataclass
class WordSearch:
    size: int
    grid: list[list[str]]
    placements: list[Placement] = field(default_factory=list)
    lang: str = "en"

    def read(self, p: Placement) -> str:
        return "".join(self.grid[y][x] for x, y in p.cells())

    def contains(self, word: str) -> bool:
        w = normalize_word(word, self.lang)
        n = self.size
        dirs = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if (dx, dy) != (0, 0)]
        for y in range(n):
            for x in range(n):
                for dx, dy in dirs:
                    ok = True
                    for i, ch in enumerate(w):
                        cx, cy = x + i * dx, y + i * dy
                        if not (0 <= cx < n and 0 <= cy < n) or self.grid[cy][cx] != ch:
                            ok = False
                            break
                    if ok:
                        return True
        return False


def normalize_word(word: str, lang: str) -> str:
    w = "".join(ch for ch in unicodedata.normalize("NFC", word) if not ch.isspace())
    if lang == "ar":
        # strip tashkeel (diacritics) and tatweel; unify alef forms
        w = "".join(ch for ch in w if not unicodedata.category(ch) == "Mn" and ch != "ـ")
        w = w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
        return w
    return w.upper()


def generate(words: list[str], lang: str = "en", difficulty: str = "easy", seed: int | None = None,
             size: int | None = None) -> WordSearch:
    rng = random.Random(seed)
    clean = [normalize_word(w, lang) for w in words if w and w.strip()]
    clean = [w for w in dict.fromkeys(clean) if len(w) >= 2]
    if not clean:
        raise ValueError("word search needs at least one word")
    longest = max(len(w) for w in clean)
    n = size or max(longest + 1, 8 if difficulty == "easy" else 11 if difficulty == "medium" else 14)
    if lang == "ar":
        dirs = DIRS_EASY_AR if difficulty == "easy" else DIRS_HARD_AR
        alphabet = AR_ALPHABET
    else:
        dirs = DIRS_EASY_EN if difficulty == "easy" else DIRS_HARD_EN
        alphabet = EN_ALPHABET
    for _attempt in range(50):
        grid: list[list[str | None]] = [[None] * n for _ in range(n)]
        placements: list[Placement] = []
        ok = True
        for w in sorted(clean, key=len, reverse=True):
            spots = []
            for dx, dy in dirs:
                for y in range(n):
                    for x in range(n):
                        ex, ey = x + dx * (len(w) - 1), y + dy * (len(w) - 1)
                        if not (0 <= ex < n and 0 <= ey < n):
                            continue
                        if all(grid[y + i * dy][x + i * dx] in (None, w[i]) for i in range(len(w))):
                            spots.append((x, y, dx, dy))
            if not spots:
                ok = False
                break
            x, y, dx, dy = rng.choice(spots)
            for i, ch in enumerate(w):
                grid[y + i * dy][x + i * dx] = ch
            placements.append(Placement(w, x, y, dx, dy))
        if ok:
            filled = [[c if c is not None else rng.choice(alphabet) for c in row] for row in grid]
            return WordSearch(n, filled, placements, lang)
        n += 1
    raise ValueError("could not place all words")


def to_html(ws: WordSearch, cell_mm: float, answer_key: bool = False) -> str:
    key_cells = {c for p in ws.placements for c in p.cells()} if answer_key else set()
    rows = []
    for y, row in enumerate(ws.grid):
        tds = "".join(
            f'<td class="{"hit" if (x, y) in key_cells else ""}">{escape(ch)}</td>' for x, ch in enumerate(row)
        )
        rows.append(f"<tr>{tds}</tr>")
    return (f'<table class="ws" dir="ltr" style="--cell:{cell_mm:.2f}mm">' + "".join(rows) + "</table>")
