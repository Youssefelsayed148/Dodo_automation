<!-- prompt: propose_formats v1 -->
Design book FORMATS for a new original book.

Formula of the liked book:
{recipe}

Chosen theme: {theme}

A format is a named mix of page-type blocks with integer shares summing to exactly 100. Allowed page types: {page_types}
(Image pages: single_character, scene, pattern_mandala, hidden_objects_scene. Code-drawn pages: maze, dot_to_dot, word_search, trace_write, qa_page, story_text.)
Front/back matter (title page, belongs-to page, end page) is added automatically; do not include it.

{instruction}

{originality_rule}

Propose formats that fit both the formula (age, detail level) and the theme. Each needs a short name, a one-sentence description and blocks.
Return {"formats": [{"name": "...", "description": "...", "blocks": [{"type": "scene", "share": 60}, ...]}, ...]}.
