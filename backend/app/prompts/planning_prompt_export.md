<!-- prompt: planning_prompt_export v1 -->
You are helping me plan an original children's book. Everything you need is below.

{brief}

TASK
Plan exactly {page_count} pages in this fixed order of page types:
{slots_json}

For every page return an object with:
- "index": page number starting at 1
- "type": the page type exactly as listed
- "description": one line describing what is drawn (distinct for every page)
- "characters": names of characters on the page
- "prompt": for image page types (single_character, scene, pattern_mandala, hidden_objects_scene) a complete image-generation prompt for black-and-white line art that follows the line-art rules; empty string for other types
- "text_content": for story_text {"text"}, qa_page {"question","choices","answer"}, word_search {"words"}, trace_write {"text"}, maze {"difficulty"}, dot_to_dot {"shape"}; otherwise {}

OUTPUT FORMAT
Reply with ONE JSON object only, no commentary, matching this schema:
{schema}
