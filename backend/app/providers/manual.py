"""Manual text/vision "provider": the prompt becomes a ChatGPT task.

No call is made: `request_text` returns the user's validated answer or raises
AwaitingManual (the job waits). Used by the registry in manual mode.
"""

from __future__ import annotations

from typing import Any

from .base import TextLLM, VisionLLM
from .jsonutil import extract_json


class ManualTextLLM(TextLLM, VisionLLM):
    name = "manual"
    model = "chatgpt"
    manual = True  # structured() skips its repair round trip (validation happens at submit time)

    def complete(self, prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> str | dict:
        from ..services.manual import request_text, text_prompt

        meta = dict(kw.get("meta") or {})
        shown = text_prompt(prompt, schema, refs_count=len(meta.get("refs") or []))
        raw = request_text(meta.get("task") or "text", shown, model_name=meta.get("model"), meta=meta)
        return extract_json(raw) if schema is not None else raw

    def analyze(self, images: list[bytes], prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> dict:
        # The user attaches the pictures in ChatGPT; the task lists them (meta.refs) for download.
        out = self.complete(prompt, schema, **kw)
        return out if isinstance(out, dict) else extract_json(out)
