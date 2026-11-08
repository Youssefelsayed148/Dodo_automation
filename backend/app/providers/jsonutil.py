"""Extract a JSON object from model text (tolerates code fences / prose)."""

from __future__ import annotations

import json
import re
from typing import Any


class JSONExtractError(ValueError):
    pass


def extract_json(text: str) -> Any:
    if isinstance(text, (dict, list)):
        return text
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    # first balanced {...} or [...]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = s.find(open_c)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(s)):
                c = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == open_c:
                    depth += 1
                elif c == close_c:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start : i + 1])
                        except json.JSONDecodeError:
                            break
            start = s.find(open_c, start + 1)
    raise JSONExtractError(f"no JSON object found in model output: {text[:200]!r}")
