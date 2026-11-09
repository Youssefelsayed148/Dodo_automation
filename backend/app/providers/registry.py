"""Pick provider implementations from configuration / settings."""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .base import ImageProvider, ProviderError, TextLLM, VisionLLM
from .mock import MockImageProvider, MockTextLLM, MockVisionLLM

IMAGE_PROVIDERS = ("mock", "openai", "gemini")
_overrides: dict[str, Any] = {}


def set_override(kind: str, provider: Any | None) -> None:
    """Tests: force a provider instance for 'image' | 'text' | 'vision'."""
    if provider is None:
        _overrides.pop(kind, None)
    else:
        _overrides[kind] = provider


def clear_overrides() -> None:
    _overrides.clear()


def available_image_providers() -> list[dict[str, Any]]:
    s = get_settings()
    return [
        {"name": "mock", "model": MockImageProvider.model, "configured": True},
        {"name": "openai", "model": s.openai_image_model, "configured": bool(s.openai_api_key)},
        {"name": "gemini", "model": s.gemini_image_model, "configured": bool(s.gemini_api_key)},
    ]


def get_image_provider(name: str | None = None) -> ImageProvider:
    if "image" in _overrides and name in (None, "", "override"):
        return _overrides["image"]
    s = get_settings()
    name = name or s.image_provider
    if name == "mock":
        return MockImageProvider()
    if name == "openai":
        from .image_http import OpenAIImageProvider

        return OpenAIImageProvider(s.openai_api_key, s.openai_image_model, s.openai_base_url, s.http_timeout)
    if name == "manual":
        raise ProviderError("IMAGE_PROVIDER=manual only works in manual mode (images come from ChatGPT)")
    if name == "gemini":
        from .image_http import GeminiImageProvider

        return GeminiImageProvider(s.gemini_api_key, s.gemini_image_model, s.gemini_base_url, s.http_timeout)
    raise ProviderError(f"unknown image provider '{name}'")


def _anthropic() -> Any:
    from .anthropic_llm import AnthropicLLM

    s = get_settings()
    return AnthropicLLM(s.anthropic_api_key, s.anthropic_model, s.anthropic_base_url, s.http_timeout)


def manual_active() -> bool:
    from ..services.manual import is_manual

    return is_manual()


def get_text_llm() -> TextLLM:
    if "text" in _overrides:
        return _overrides["text"]
    if manual_active():
        from .manual import ManualTextLLM

        return ManualTextLLM()
    return _anthropic() if get_settings().text_provider == "anthropic" else MockTextLLM()


def get_vision_llm() -> VisionLLM:
    if "vision" in _overrides:
        return _overrides["vision"]
    if manual_active():
        from .manual import ManualTextLLM

        return ManualTextLLM()
    return _anthropic() if get_settings().vision_provider == "anthropic" else MockVisionLLM()
