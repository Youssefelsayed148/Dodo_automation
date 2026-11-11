<!-- prompt: analyze_theme v1 -->
You are designing the style formula for a new children's book (coloring book, sticker book or activity book) from a theme or idea the user gave. There is no reference book: design the formula that best fits THIS theme and its natural audience.

{originality_rule}

The user's theme / idea (it may also be a short description of a kind of book they like):
---
{theme}
---

Decide, specifically for this theme (do not give a generic answer):
- mood: 2-5 words that fit the theme (e.g. "cheerful and cozy")
- age_group: e.g. "2-4", "4-8", "8-12", "adult" - infer it from the theme and the way it is written
- line_weight: one of "thin", "medium", "bold", "extra bold" - younger children need bolder lines
- detail_level: one of "very low", "low", "medium", "high"
- page_mix: list of {"type", "share"} using ONLY these page types: {page_types}. Choose the page types that make this theme fun (for example a space theme suits scenes, mazes and dot-to-dot; a school theme suits trace_write, word_search and qa_page). Shares are percentages summing to 100.
- confidence: "{expected_confidence}" unless the theme is too vague to design for, then "low"
- notes: 1-3 sentences about the drawing style and layout that suit this theme (shapes, composition, how characters and backgrounds should look). No names, no titles, no brands.

Do not output any existing character name, book title, author, series or brand.
