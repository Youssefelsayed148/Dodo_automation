"""Versioned prompt files (app/prompts/*.md) with {placeholders}.

Only `{identifier}` tokens are substituted, so literal JSON braces in prompt
text are safe. Every prompt automatically gets {originality_rule} and
{no_text_rule}.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_VERSION = re.compile(r"<!--\s*prompt:\s*([a-z_]+)\s+v(\d+)\s*-->")

ORIGINALITY_RULE = (
    "ORIGINALITY RULE: Only the abstract formula of the reference book may be reused "
    "(mood, structure, page mix, detail level, age group). Never reuse or mention its "
    "characters, character names, titles, scenes, text, brand names or trademarks. "
    "Everything you produce must be original."
)
NO_TEXT_RULE = (
    "NO TEXT RULE: Images must never contain letters, words, numbers, signs, labels or "
    "watermarks. All text is added later by code."
)


class PromptError(KeyError):
    pass


@lru_cache
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"prompt file not found: {name}.md")
    return path.read_text(encoding="utf-8")


def prompt_version(name: str) -> int:
    m = _VERSION.search(load_prompt(name))
    return int(m.group(2)) if m else 1


def fill(template: str, variables: dict[str, Any]) -> str:
    values = {"originality_rule": ORIGINALITY_RULE, "no_text_rule": NO_TEXT_RULE, **variables}
    missing: list[str] = []

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in values:
            missing.append(key)
            return m.group(0)
        v = values[key]
        return v if isinstance(v, str) else str(v)

    out = _PLACEHOLDER.sub(repl, template)
    if missing:
        raise PromptError(f"missing placeholder values: {sorted(set(missing))}")
    # strip version comment
    return _VERSION.sub("", out).strip()


def render(name: str, variables: dict[str, Any] | None = None) -> str:
    return fill(load_prompt(name), variables or {})


def list_prompts() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
