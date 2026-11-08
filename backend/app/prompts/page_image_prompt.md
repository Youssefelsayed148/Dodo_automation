<!-- prompt: page_image_prompt v1 -->
Write the final image-generation prompt for one coloring-book page.

Page type: {page_type}
Scene: {description}
Characters on this page (keep them identical to the attached character sheet):
{characters}

Style rules (style anchor, must be followed exactly):
{style_rules}

Problems found in previous attempts that must be avoided: {issues}

The prompt must ask for: clean black outlines on pure white, no grey, no shading, no filled black areas, closed shapes suitable for coloring, the whole subject inside the page with a margin, simple background matching the detail level.
{no_text_rule}

Return {"prompt": "..."}.
