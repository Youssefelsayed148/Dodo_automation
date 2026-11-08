<!-- prompt: character_edit v1 -->
You are revising an image-generation prompt for a coloring-book character. The selected image is used as a reference, so only the requested change should differ.

Character: {character}
Current prompt:
{base_prompt}

User's change request: "{instruction}"

Rewrite the prompt so that ONLY the requested change is applied and every other detail (proportions, signature feature, outfit, line style, pose framing) is explicitly kept the same. Keep it black and white line art with no shading.
{no_text_rule}

Return {"prompt": "...", "changed": "short summary of what changed"}.
