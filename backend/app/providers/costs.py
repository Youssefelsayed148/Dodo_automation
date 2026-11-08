"""Cost estimates (USD). Values are estimates; override with COST_TABLE env:
COST_TABLE="openai:gpt-image-1=0.04,anthropic:claude-opus-5-5:in=4,anthropic:claude-opus-5-5:out=20"
(text prices are USD per 1M tokens, image prices USD per image)."""

from __future__ import annotations

import os

# USD per 1M tokens (input, output)
TEXT_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
# USD per generated image (rough defaults; verify against your provider's pricing)
IMAGE_PRICES: dict[str, float] = {
    "gpt-image-1": 0.04,
    "gemini-2.5-flash-image": 0.039,
}


def _overrides() -> dict[str, float]:
    out: dict[str, float] = {}
    for part in os.environ.get("COST_TABLE", "").split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


def estimate_text_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    o = _overrides()
    pin, pout = TEXT_PRICES.get(model, (0.0, 0.0))
    pin = o.get(f"{provider}:{model}:in", pin)
    pout = o.get(f"{provider}:{model}:out", pout)
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)


def estimate_image_cost(provider: str, model: str, n: int = 1) -> float:
    o = _overrides()
    price = o.get(f"{provider}:{model}", IMAGE_PRICES.get(model, 0.0))
    return round(price * n, 6)
