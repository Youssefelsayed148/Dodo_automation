"""Structured LLM calls: render prompt -> call provider -> validate with
Pydantic -> one automatic repair retry on invalid output."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..providers.base import TextLLM, VisionLLM
from ..providers.jsonutil import JSONExtractError, extract_json
from ..providers.registry import get_text_llm, get_vision_llm
from .prompts import render

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMOutputError(ValueError):
    pass


REPAIR_TEMPLATE = (
    "Your previous answer was not valid for the required JSON schema.\n"
    "Error: {error}\n\nPrevious answer:\n{previous}\n\n"
    "Return ONLY a corrected JSON object that matches this schema:\n{schema}"
)


def _parse(raw: Any, model: type[T]) -> T:
    data = raw if isinstance(raw, (dict, list)) else extract_json(str(raw))
    return model.model_validate(data)


def structured(
    task: str,
    variables: dict[str, Any],
    model: type[T],
    *,
    images: list[bytes] | None = None,
    text_llm: TextLLM | None = None,
    vision_llm: VisionLLM | None = None,
    prompt: str | None = None,
    meta: dict[str, Any] | None = None,
) -> T:
    """`meta` adds task metadata (manual mode: refs, expected_count, count_field)."""
    prompt = prompt if prompt is not None else render(task, variables)
    schema = model.model_json_schema()
    base_meta = {"task": task, "vars": variables, "model": model.__name__, **(meta or {})}
    llm: Any = (vision_llm or get_vision_llm()) if images else (text_llm or get_text_llm())

    def call(p: str, attempt: int) -> Any:
        m = {**base_meta, "attempt": attempt}
        if images:
            return llm.analyze(images, p, schema, meta=m)
        return llm.complete(p, schema, meta=m)

    if getattr(llm, "manual", False):
        # Manual mode: the answer was validated when the user submitted it; no repair round trip.
        raw = call(prompt, 0)
        try:
            return _parse(raw, model)
        except (ValidationError, JSONExtractError, ValueError) as e:
            raise LLMOutputError(f"{task}: stored ChatGPT answer is invalid: {e}") from e

    raw = call(prompt, 0)
    try:
        return _parse(raw, model)
    except (ValidationError, JSONExtractError, ValueError) as e:
        log.warning("invalid LLM output for %s, repairing: %s", task, e)
        repair = REPAIR_TEMPLATE.format(
            error=str(e)[:1500],
            previous=(json.dumps(raw) if isinstance(raw, (dict, list)) else str(raw))[:6000],
            schema=json.dumps(schema),
        )
        raw2 = call(prompt + "\n\n" + repair, 1)
        try:
            return _parse(raw2, model)
        except (ValidationError, JSONExtractError, ValueError) as e2:
            raise LLMOutputError(f"{task}: model output invalid after repair: {e2}") from e2
