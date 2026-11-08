"""Mock providers: zero-cost, offline, deterministic.

MockImageProvider draws simple black-outline placeholder line art (never text).
MockTextLLM / MockVisionLLM return schema-valid canned JSON, keyed on the
`task` name the services pass via `meta`.
"""

from __future__ import annotations

import hashlib
import io
import json
import random
from typing import Any

from PIL import Image, ImageDraw

from .base import ImageProvider, TextLLM, VisionLLM, record_usage

THEME_WORDS = ["Garden", "Bakery", "Ocean", "Forest", "Space", "Farm", "Castle", "Jungle", "Snow", "Market"]
SCENE_PLACES = [
    "in a sunny meadow", "beside a little river", "on a cozy porch", "at a busy market stall",
    "under a big oak tree", "on a sandy beach", "inside a warm kitchen", "near a wooden bridge",
    "on a hilltop at sunrise", "in a flower field", "at a picnic blanket", "beside a lighthouse",
    "in a vegetable patch", "on a snowy path", "inside a treehouse", "at a tiny train station",
]
SCENE_ACTIONS = [
    "waters the plants", "bakes round cookies", "flies a kite", "reads a big book", "builds a sandcastle",
    "plants a seed", "carries a basket of apples", "paints a fence", "waves hello", "chases butterflies",
    "stacks wooden blocks", "rides a small bicycle", "feeds the ducks", "hangs paper lanterns",
    "picks strawberries", "splashes in puddles", "decorates a cake", "looks through a telescope",
]


def _rng(*parts: Any) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


class MockImageProvider(ImageProvider):
    name = "mock"
    model = "mock-lineart-1"

    def __init__(self, max_side: int = 1024):
        self.max_side = max_side
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt, size_hint=(1024, 1024), reference_images=None, seed=None) -> bytes:
        self.calls.append({"prompt": prompt, "size_hint": size_hint, "refs": len(reference_images or []), "seed": seed})
        w, h = size_hint
        scale = min(1.0, self.max_side / max(w, h))
        w, h = max(64, int(w * scale)), max(64, int(h * scale))
        img = Image.new("L", (w, h), 255)
        d = ImageDraw.Draw(img)
        r = _rng(prompt, seed)
        lw = max(2, int(min(w, h) * 0.008))
        m = int(min(w, h) * 0.12)  # keep subject away from edges
        # ground line
        gy = int(h * 0.78)
        d.line([(m, gy), (w - m, gy)], fill=0, width=lw)
        # a few background shapes
        for _ in range(r.randint(2, 4)):
            cx, cy = r.randint(m * 2, w - m * 2), r.randint(m * 2, gy - m)
            rad = r.randint(int(min(w, h) * 0.04), int(min(w, h) * 0.1))
            if r.random() < 0.5:
                d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=0, width=lw)
            else:
                d.rectangle([cx - rad, cy - rad, cx + rad, cy + rad], outline=0, width=lw)
        # "character": head + body + ears + eyes (all outlines)
        cx = w // 2 + r.randint(-w // 10, w // 10)
        head_r = int(min(w, h) * 0.13)
        hy = gy - int(min(w, h) * 0.38)
        body_w, body_h = int(head_r * 1.3), int(head_r * 1.5)
        d.ellipse([cx - body_w, hy + head_r * 0.8, cx + body_w, hy + head_r * 0.8 + body_h * 1.6], outline=0, width=lw)
        d.ellipse([cx - head_r, hy - head_r, cx + head_r, hy + head_r], outline=0, width=lw)
        for sx in (-1, 1):
            ex = cx + sx * int(head_r * 0.6)
            d.ellipse([ex - head_r * 0.3, hy - head_r * 1.5, ex + head_r * 0.3, hy - head_r * 0.7], outline=0, width=lw)
            d.ellipse([cx + sx * head_r * 0.35 - lw * 2, hy - lw * 2, cx + sx * head_r * 0.35 + lw * 2, hy + lw * 2], outline=0, width=lw)
        d.arc([cx - head_r * 0.4, hy, cx + head_r * 0.4, hy + head_r * 0.6], 20, 160, fill=0, width=lw)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        record_usage(self.name, self.model, "image", 1, 0.0)
        return buf.getvalue()


# --------------------------------------------------------------------- canned


def _canned(task: str, v: dict[str, Any]) -> dict[str, Any]:
    r = _rng(task, json.dumps(v, sort_keys=True, default=str)[:2000])
    if task == "analyze_source":
        return {
            "mood": "cheerful and cozy",
            "age_group": "4-8",
            "line_weight": "bold",
            "detail_level": "low",
            "page_mix": [{"type": "scene", "share": 60}, {"type": "single_character", "share": 30}, {"type": "maze", "share": 10}],
            "confidence": v.get("expected_confidence", "medium"),
            "notes": "Simple rounded animal characters, thick outlines, large open areas.",
        }
    if task == "propose_themes":
        words = r.sample(THEME_WORDS, 3)
        return {
            "themes": [
                {"title": f"Little {w} Friends", "description": f"Gentle everyday adventures of small animal friends around the {w.lower()}."}
                for w in words
            ]
        }
    if task == "propose_formats":
        base = [
            {"name": "Classic coloring", "description": "Mostly scenes with a few character portraits.",
             "blocks": [{"type": "scene", "share": 70}, {"type": "single_character", "share": 30}]},
            {"name": "Color and play", "description": "Coloring mixed with light puzzles.",
             "blocks": [{"type": "scene", "share": 50}, {"type": "single_character", "share": 20}, {"type": "maze", "share": 15}, {"type": "word_search", "share": 15}]},
            {"name": "Story and color", "description": "A short story with coloring pages and questions.",
             "blocks": [{"type": "scene", "share": 60}, {"type": "story_text", "share": 20}, {"type": "qa_page", "share": 20}]},
        ]
        if v.get("instruction_raw"):
            base = [{"name": "Custom hybrid", "description": f"Hybrid: {str(v['instruction_raw'])[:80]}",
                     "blocks": [{"type": "scene", "share": 40}, {"type": "dot_to_dot", "share": 20}, {"type": "trace_write", "share": 20}, {"type": "maze", "share": 20}]}]
        return {"formats": base}
    if task == "plan_pages":
        slots = v.get("slots") or []
        chars = v.get("character_names") or []
        lang = v.get("book_language", "en")
        pages = []
        for i, t in enumerate(slots):
            place = SCENE_PLACES[i % len(SCENE_PLACES)]
            action = SCENE_ACTIONS[(i * 7) % len(SCENE_ACTIONS)]
            who = chars[i % len(chars)] if chars else "a small bear"
            desc = f"{who} {action} {place} (page {i + 1})"
            pages.append({"type": t, "description": desc, "characters": [who] if chars else [], "text_content": _mock_text_content(t, i, lang)})
        return {"pages": pages}
    if task == "character_brief":
        names = ["Pip", "Mila", "Toto", "Zed"]
        species = ["bear cub", "bunny", "duckling", "hedgehog"]
        feats = ["a patched left ear", "a striped scarf", "a tiny flower behind one ear", "round glasses"]
        n = int(v.get("count", 2))
        return {
            "characters": [
                {"name": names[i % 4], "species": species[i % 4], "personality": "curious and kind",
                 "proportions": "big round head, small body, short legs", "signature_feature": feats[i % 4], "outfit": "simple overalls"}
                for i in range(n)
            ]
        }
    if task == "character_edit":
        return {"prompt": f"{v.get('base_prompt', '')} Change only: {v.get('instruction', '')}.".strip(), "changed": str(v.get("instruction", ""))}
    if task == "page_image_prompt":
        return {"prompt": f"Black and white coloring page line art: {v.get('description', '')}"}
    if task == "story_text":
        return {"text": "The friends shared their cookies and laughed all afternoon." if v.get("book_language") != "ar" else "تقاسم الأصدقاء الكعك وضحكوا طوال الظهيرة."}
    if task == "qa_content":
        return {"ok": True, "issues": []}
    if task in ("qa_vision_check", "consistency_check"):
        return {"pass": True, "issues": [], "checks": {"line_art": True}}
    return {}


def _mock_text_content(t: str, i: int, lang: str) -> dict[str, Any]:
    ar = lang == "ar"
    if t == "story_text":
        return {"text": "ذهب الأصدقاء إلى الحديقة وزرعوا بذرة صغيرة." if ar else f"Part {i + 1}: the friends planted a tiny seed and watched it grow."}
    if t == "qa_page":
        return {"question": "ما لون الشمس؟" if ar else "What color is the sun?", "choices": ["أصفر", "أزرق", "أخضر"] if ar else ["Yellow", "Blue", "Green"], "answer": 0}
    if t == "word_search":
        return {"words": ["شمس", "قمر", "نجم", "بحر", "ورد"] if ar else ["SUN", "TREE", "BIRD", "SEED", "RAIN", "LEAF"]}
    if t == "trace_write":
        return {"text": "سلام" if ar else "Hello"}
    if t == "maze":
        return {"difficulty": "easy"}
    if t == "dot_to_dot":
        return {"shape": ["star", "heart", "house", "fish"][i % 4]}
    return {}


class MockTextLLM(TextLLM):
    name = "mock"
    model = "mock-text-1"

    def __init__(self, overrides: dict[str, Any] | None = None):
        self.overrides = overrides or {}
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt, schema=None, **kw):
        meta = kw.get("meta") or {}
        task = meta.get("task", "")
        self.calls.append({"task": task, "prompt": prompt})
        record_usage(self.name, self.model, "text", len(prompt) // 4, 0.0)
        if task in self.overrides:
            o = self.overrides[task]
            out = o(prompt, meta) if callable(o) else o
        else:
            out = _canned(task, meta.get("vars") or {})
        if schema is None:
            return out if isinstance(out, str) else json.dumps(out)
        return out


class MockVisionLLM(VisionLLM):
    name = "mock"
    model = "mock-vision-1"

    def __init__(self, overrides: dict[str, Any] | None = None):
        self.overrides = overrides or {}
        self.calls: list[dict[str, Any]] = []

    def analyze(self, images, prompt, schema=None, **kw):
        meta = kw.get("meta") or {}
        task = meta.get("task", "")
        self.calls.append({"task": task, "n_images": len(images), "prompt": prompt})
        record_usage(self.name, self.model, "vision", len(images), 0.0)
        if task in self.overrides:
            o = self.overrides[task]
            return o(prompt, meta) if callable(o) else o
        return _canned(task, meta.get("vars") or {})
