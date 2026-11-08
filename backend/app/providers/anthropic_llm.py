"""Claude via the official Anthropic SDK, implementing TextLLM and VisionLLM.

The model id comes from configuration (ANTHROPIC_MODEL). Retries/backoff are
handled by `with_retries` (SDK retries disabled so the policy lives in one
place) and every call writes a UsageLog row via `record_usage`.
"""

from __future__ import annotations

import base64
from typing import Any

from .base import ProviderError, RetryableError, TextLLM, VisionLLM, record_usage, with_retries
from .costs import estimate_text_cost
from .jsonutil import extract_json


def _media_type(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/png"


class AnthropicLLM(TextLLM, VisionLLM):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: str | None = None, timeout: float = 120.0,
                 effort: str = "medium", client: Any = None):
        if not api_key and client is None:
            raise ProviderError("ANTHROPIC_API_KEY is not set")
        self.model = model
        self.effort = effort
        if client is not None:
            self.client = client
        else:
            import anthropic  # lazy: keeps the mock pipeline dependency-free

            self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None, timeout=timeout, max_retries=0)

    # -------------------------------------------------------------- internals

    def _call(self, content: list[dict[str, Any]], system: str | None, max_tokens: int = 16000) -> str:
        def once() -> Any:
            try:
                import anthropic  # noqa: F401
                errors = anthropic
            except ImportError:  # pragma: no cover - injected test client
                errors = None
            try:
                kwargs: dict[str, Any] = {
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": content}],
                    "output_config": {"effort": self.effort},
                }
                if system:
                    kwargs["system"] = system
                return self.client.messages.create(**kwargs)
            except Exception as e:  # map SDK errors onto our retry policy
                if errors is not None:
                    if isinstance(e, (errors.RateLimitError, errors.APIConnectionError, errors.APITimeoutError)):
                        raise RetryableError(str(e)) from e
                    if isinstance(e, errors.APIStatusError):
                        if e.status_code >= 500 or e.status_code in (408, 409, 429):
                            raise RetryableError(str(e)) from e
                        raise ProviderError(f"Anthropic API error {e.status_code}: {e}") from e
                raise

        resp = with_retries(once)
        if getattr(resp, "stop_reason", None) == "refusal":
            raise ProviderError("The model declined this request")
        usage = getattr(resp, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        record_usage(self.name, self.model, "text", in_tok + out_tok,
                     estimate_text_cost(self.name, self.model, in_tok, out_tok),
                     input_tokens=in_tok, output_tokens=out_tok)
        return "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")

    @staticmethod
    def _json_instruction(schema: dict[str, Any] | None) -> str:
        if not schema:
            return ""
        import json

        return ("\n\nRespond with a single JSON object only (no prose, no code fences) "
                "that validates against this JSON schema:\n" + json.dumps(schema))

    # -------------------------------------------------------------- interface

    def complete(self, prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> str | dict:
        text = self._call([{"type": "text", "text": prompt + self._json_instruction(schema)}], kw.get("system"))
        return extract_json(text) if schema is not None else text

    def analyze(self, images: list[bytes], prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> dict:
        content: list[dict[str, Any]] = []
        for img in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": _media_type(img),
                                                          "data": base64.standard_b64encode(img).decode("ascii")}})
        content.append({"type": "text", "text": prompt + self._json_instruction(schema or {"type": "object"})})
        return extract_json(self._call(content, kw.get("system")))
