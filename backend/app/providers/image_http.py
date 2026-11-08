"""Real image providers over HTTP (httpx). Provider/model names come from config.

- OpenAIImageProvider: /v1/images/generations, or /v1/images/edits when
  reference images are given (reference-image support).
- GeminiImageProvider: models/{model}:generateContent with inline reference
  images and IMAGE response modality.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .anthropic_llm import _media_type
from .base import ImageProvider, ProviderError, RetryableError, classify_http_status, record_usage, with_retries
from .costs import estimate_image_cost


def _aspect(size: tuple[int, int]) -> float:
    w, h = size
    return w / h if h else 1.0


class _HTTPImageProvider(ImageProvider):
    def __init__(self, api_key: str, model: str, base_url: str, timeout: float = 120.0,
                 transport: httpx.BaseTransport | None = None):
        if not api_key:
            raise ProviderError(f"API key for image provider '{self.name}' is not set")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport)

    def _send(self, fn) -> dict[str, Any]:
        def once():
            try:
                with self._client() as c:
                    r = fn(c)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                raise RetryableError(str(e)) from e
            if r.status_code >= 300:
                classify_http_status(r.status_code, r.text, r.headers.get("retry-after"))
            return r.json()

        return with_retries(once)


class OpenAIImageProvider(_HTTPImageProvider):
    name = "openai"

    @staticmethod
    def size_for(size_hint: tuple[int, int]) -> str:
        a = _aspect(size_hint)
        if a < 0.9:
            return "1024x1536"
        if a > 1.1:
            return "1536x1024"
        return "1024x1024"

    def generate(self, prompt, size_hint=(1024, 1024), reference_images=None, seed=None) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        size = self.size_for(size_hint)
        refs = reference_images or []
        if refs:
            files = [("image[]", (f"ref{i}.png", data, _media_type(data))) for i, data in enumerate(refs[:4])]
            data = {"model": self.model, "prompt": prompt, "size": size, "n": "1"}
            body = self._send(lambda c: c.post(f"{self.base_url}/v1/images/edits", headers=headers, data=data, files=files))
        else:
            payload = {"model": self.model, "prompt": prompt, "size": size, "n": 1}
            body = self._send(lambda c: c.post(f"{self.base_url}/v1/images/generations", headers=headers, json=payload))
        try:
            b64 = body["data"][0]["b64_json"]
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"unexpected OpenAI image response: {str(body)[:300]}") from e
        record_usage(self.name, self.model, "image", 1, estimate_image_cost(self.name, self.model))
        return base64.b64decode(b64)


class GeminiImageProvider(_HTTPImageProvider):
    name = "gemini"

    @staticmethod
    def aspect_ratio(size_hint: tuple[int, int]) -> str:
        a = _aspect(size_hint)
        options = {"1:1": 1.0, "3:4": 0.75, "4:3": 4 / 3, "2:3": 2 / 3, "3:2": 1.5, "9:16": 9 / 16, "16:9": 16 / 9}
        return min(options, key=lambda k: abs(options[k] - a))

    def generate(self, prompt, size_hint=(1024, 1024), reference_images=None, seed=None) -> bytes:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for data in (reference_images or [])[:4]:
            parts.append({"inline_data": {"mime_type": _media_type(data), "data": base64.b64encode(data).decode("ascii")}})
        gen_cfg: dict[str, Any] = {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": self.aspect_ratio(size_hint)}}
        if seed is not None:
            gen_cfg["seed"] = seed
        payload = {"contents": [{"parts": parts}], "generationConfig": gen_cfg}
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        body = self._send(lambda c: c.post(url, headers={"x-goog-api-key": self.api_key}, json=payload))
        try:
            for cand in body.get("candidates", []):
                for p in cand.get("content", {}).get("parts", []):
                    inline = p.get("inlineData") or p.get("inline_data")
                    if inline and inline.get("data"):
                        record_usage(self.name, self.model, "image", 1, estimate_image_cost(self.name, self.model))
                        return base64.b64decode(inline["data"])
        except AttributeError:
            pass
        raise ProviderError(f"Gemini returned no image: {str(body)[:300]}")
