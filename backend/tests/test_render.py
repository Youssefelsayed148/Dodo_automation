import pytest

from app.render import dot_to_dot, html, maze, word_search
from app.services.specs import page_spec

from .conftest import needs_weasy


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
@pytest.mark.parametrize("seed", range(5))
def test_maze_solvable(difficulty, seed):
    m = maze.for_page(difficulty, 0.75, seed=seed)
    path = m.solve()
    assert path is not None and path[0] == m.start and path[-1] == m.end
    # perfect maze: every cell reachable
    seen, stack = {m.start}, [m.start]
    while stack:
        for nb in m.neighbors(*stack.pop()):
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    assert len(seen) == m.cols * m.rows


def test_maze_difficulty_scales():
    assert maze.for_page("hard", 1.0, 1).cols > maze.for_page("easy", 1.0, 1).cols


def test_maze_svg_has_walls():
    svg = maze.to_svg(maze.generate(5, 5, seed=1), 500, 500)
    assert svg.startswith("<svg") and svg.count("<line") > 10


@pytest.mark.parametrize("difficulty", ["easy", "hard"])
def test_word_search_contains_all_words_en(difficulty):
    words = ["sun", "tree", "bird", "seed", "rain", "leaf", "flower"]
    ws = word_search.generate(words, "en", difficulty, seed=3)
    for w in words:
        assert ws.contains(w), w
    for p in ws.placements:
        assert ws.read(p) == p.word


def test_word_search_arabic_rtl():
    words = ["شمس", "قمر", "نجمة", "بحر", "وردة"]
    ws = word_search.generate(words, "ar", "easy", seed=2)
    for w in words:
        assert ws.contains(w)
    for p in ws.placements:
        assert p.dx in (-1, 0)  # never left-to-right in Arabic
    assert all(ch in word_search.AR_ALPHABET for row in ws.grid for ch in row)


def test_dot_to_dot_numbers_all_points():
    for shape in dot_to_dot.SHAPES:
        svg = dot_to_dot.to_svg(shape, 600, 800)
        n = len(dot_to_dot.points_for(shape))
        assert svg.count("<circle") == n
        assert f">{n}</text>" in svg


def test_html_fragments_direction_and_text():
    sp = page_spec("8.5x11in", True)
    frag = html.page_fragment("story_text", {"text": "ذهب الأصدقاء إلى الحديقة"}, sp, "ar")
    assert 'dir="rtl"' in frag and 'lang="ar"' in frag and "الحديقة" in frag
    frag_en = html.page_fragment("qa_page", {"question": "What color?", "choices": ["Red", "Blue"]}, sp, "en")
    assert 'dir="ltr"' in frag_en and frag_en.count('class="qa-choice"') == 2
    doc = html.document([frag], sp, "ar")
    assert '<html lang="ar" dir="rtl">' in doc and "size: 8.75in 11.25in" in doc
    for t in ("maze", "dot_to_dot", "word_search", "trace_write", "title_page", "belongs_to_page", "end_page"):
        content = {"words": ["SUN", "TREE"], "text": "Hi", "shape": "star"}
        assert 'class="page"' in html.page_fragment(t, content, sp, "en", book_title="T", seed=1)


@needs_weasy
@pytest.mark.parametrize("lang", ["en", "ar"])
@pytest.mark.parametrize("ptype", ["maze", "word_search", "story_text", "qa_page", "dot_to_dot", "trace_write",
                                   "title_page", "belongs_to_page", "end_page"])
def test_code_pages_render_to_print_size(tmp_path, lang, ptype):
    import numpy as np
    from PIL import Image

    from app.render import render_code_page

    sp = page_spec("8.5x11in", False)
    content = {"words": ["شمس", "قمر"] if lang == "ar" else ["SUN", "MOON"], "text": "سلام" if lang == "ar" else "Hello",
               "question": "؟" if lang == "ar" else "Why?", "choices": ["أ", "ب"] if lang == "ar" else ["A", "B"],
               "shape": "heart", "difficulty": "easy"}
    out = render_code_page(ptype, content, sp, lang, tmp_path / f"{ptype}.png", book_title="كتاب" if lang == "ar" else "Book")
    with Image.open(out) as im:
        assert im.size == sp.pixel_size
        assert np.asarray(im.convert("L")).min() < 100  # something was drawn
