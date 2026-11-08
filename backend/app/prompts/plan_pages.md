<!-- prompt: plan_pages v1 -->
Plan the pages of an original children's book.

Theme: {theme}
Formula: {recipe}
Characters (use only these, by name): {characters}
Book language for any text: {book_language} ("en" = English, "ar" = Arabic; write all text_content in this language)

The page types and their order are fixed. Fill exactly {page_count} pages, in this order:
{slots_json}

For each page return:
- type: exactly as given in the order above
- description: ONE line describing what is drawn (subject, action, setting). Every description must be distinct from all others. For code-drawn pages describe the puzzle topic.
- characters: list of character names that appear (empty if none)
- text_content, by type:
  - story_text: {"text": "2-4 short sentences continuing the story"}
  - qa_page: {"question": "...", "choices": ["...", "...", "..."], "answer": index_of_correct_choice} (or omit choices for open answer lines)
  - word_search: {"words": [5-8 short theme words, uppercase if English]}
  - trace_write: {"text": "one short word or phrase to trace"}
  - maze: {"difficulty": "easy" | "medium" | "hard"} matched to the age group
  - dot_to_dot: {"shape": one of "star", "heart", "house", "fish", "circle", "tree", "cat", "balloon"}
  - image pages: {} (no text)

{originality_rule}
{no_text_rule}

Return {"pages": [...]} with exactly {page_count} items.
