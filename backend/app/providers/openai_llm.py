"""GPT text + vision over HTTP (Chat Completions, httpx - no extra dependency), implementing TextLLM and
VisionLLM. The model id comes from configuration (OPENAI_TEXT_MODEL). Same retry policy and UsageLog rows as
the Claude adapter."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from .anthropic_llm import _media_type
from .base import ProviderError, RetryableError, TextLLM, VisionLLM, classify_http_status, record_usage, with_retries
from .costs import estimate_text_cost
from .jsonutil import extract_json


class OpenAILLM(TextLLM, VisionLLM):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com", timeout: float = 120.0,
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _call(self, content: list[dict[str, Any]], system: str | None, max_tokens: int = 16000) -> str:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": content})
        payload = {"model": self.model, "messages": messages, "max_completion_tokens": max_tokens,
                   "response_format": {"type": "json_object"}}

        def once() -> dict[str, Any]:
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
                    r = c.post(f"{self.base_url}/v1/chat/completions", json=payload,
                               headers={"Authorization": f"Bearer {self.api_key}"})
            except (httpx.TimeoutException, httpx.TransportError) as e:
                raise RetryableError(str(e)) from e
            if r.status_code >= 300:
                classify_http_status(r.status_code, r.text, r.headers.get("retry-after"))
            return r.json()

        body = with_retries(once)
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected OpenAI response: {str(body)[:300]}") from e
        if msg.get("refusal"):
            raise ProviderError("The model declined this request")
        usage = body.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens") or 0)
        out_tok = int(usage.get("completion_tokens") or 0)
        record_usage(self.name, self.model, "text", in_tok + out_tok,
                     estimate_text_cost(self.name, self.model, in_tok, out_tok),
                     input_tokens=in_tok, output_tokens=out_tok)
        return msg.get("content") or ""

    @staticmethod
    def _json_instruction(schema: dict[str, Any] | None) -> str:
        if not schema:
            return ""
        return ("\n\nRespond with a single JSON object only (no prose, no code fences) "
                "that validates against this JSON schema:\n" + json.dumps(schema))

    def complete(self, prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> str | dict:
        text = self._call([{"type": "text", "text": prompt + self._json_instruction(schema)}], kw.get("system"))
        return extract_json(text) if schema is not None else text

    def analyze(self, images: list[bytes], prompt: str, schema: dict[str, Any] | None = None, **kw: Any) -> dict:
        content: list[dict[str, Any]] = []
        for img in images:
            b64 = base64.standard_b64encode(img).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:{_media_type(img)};base64,{b64}"}})
        content.append({"type": "text", "text": prompt + self._json_instruction(schema or {"type": "object"})})
        return extract_json(self._call(content, kw.get("system")))
