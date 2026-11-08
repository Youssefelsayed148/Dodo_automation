<!-- prompt: analyze_source v1 -->
You are analyzing a children's book that the user likes (coloring book, sticker book or activity book) in order to extract its abstract *formula* only.

{originality_rule}

Material available:
- Store page text (title, description, product data), may be partial:
---
{source_text}
---
- {image_count} preview/page image(s) are attached (may be zero).

Describe the formula:
- mood: 2-5 words (e.g. "cheerful and cozy")
- age_group: e.g. "2-4", "4-8", "8-12", "adult"
- line_weight: one of "thin", "medium", "bold", "extra bold"
- detail_level: one of "very low", "low", "medium", "high"
- page_mix: list of {"type", "share"} using ONLY these page types: {page_types}. Shares are percentages summing to 100.
- confidence: "{expected_confidence}" unless the material is almost unreadable, then "low"
- notes: 1-3 sentences about drawing style and layout (no names, no titles, no brands).

Do not output any character name, book title, author, series or brand from the source.
