import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app.providers import base
from app.providers.anthropic_llm import AnthropicLLM
from app.providers.base import ProviderError, RetryableError, with_retries
from app.providers.image_http import GeminiImageProvider, OpenAIImageProvider
from app.providers.mock import MockImageProvider, MockTextLLM, MockVisionLLM
from app.schemas import CharacterBriefsOut, FormatsOut, PagePlanOut, RecipeOut, ThemesOut, VisionVerdict

PNG = base64.b64encode(MockImageProvider().generate("x", (64, 64))).decode()


def test_mock_image_is_png_line_art():
    data = MockImageProvider().generate("hello", (2550, 3300), seed=1)
    im = Image.open(io.BytesIO(data))
    assert im.format == "PNG" and im.width <= 1024 and im.height > im.width


@pytest.mark.parametrize("task,model,vars", [
    ("analyze_source", RecipeOut, {}),
    ("propose_themes", ThemesOut, {}),
    ("propose_formats", FormatsOut, {}),
    ("propose_formats", FormatsOut, {"instruction_raw": "mazes and dots"}),
    ("plan_pages", PagePlanOut, {"slots": ["scene", "maze", "qa_page"], "character_names": ["Pip"]}),
    ("character_brief", CharacterBriefsOut, {"count": 2}),
])
def test_mock_text_llm_is_schema_valid(task, model, vars):
    out = MockTextLLM().complete("p", model.model_json_schema(), meta={"task": task, "vars": vars})
    model.model_validate(out)


def test_mock_vision_verdict():
    VisionVerdict.model_validate(MockVisionLLM().analyze([b"x"], "p", {}, meta={"task": "qa_vision_check"}))


def test_usage_is_recorded():
    recs = []
    base.add_usage_sink(recs.append)
    with base.usage_context(book_id=5, purpose="page"):
        MockImageProvider().generate("a", (64, 64))
    assert recs and recs[0].book_id == 5 and recs[0].kind == "image"


def test_with_retries():
    n = {"i": 0}

    def flaky():
        n["i"] += 1
        if n["i"] < 3:
            raise RetryableError("429")
        return "ok"

    assert with_retries(flaky, sleep=lambda s: None) == "ok" and n["i"] == 3
    with pytest.raises(RetryableError):
        with_retries(lambda: (_ for _ in ()).throw(RetryableError("x")), attempts=2, sleep=lambda s: None)


def test_openai_generate_and_edit():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"data": [{"b64_json": PNG}]})

    p = OpenAIImageProvider("k", "img-model", "https://api.example.com", transport=httpx.MockTransport(handler))
    assert p.generate("cat", (2550, 3300))[:4] == b"\x89PNG"
    assert seen[0].url.path == "/v1/images/generations"
    body = json.loads(seen[0].content)
    assert body["size"] == "1024x1536" and body["model"] == "img-model"
    p.generate("cat", (1000, 1000), reference_images=[base64.b64decode(PNG)])
    assert seen[1].url.path == "/v1/images/edits"
    assert seen[0].headers["authorization"] == "Bearer k"


def test_openai_retries_429_then_errors_on_400(monkeypatch):
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    codes = iter([429, 200])

    def handler(req):
        c = next(codes)
        return httpx.Response(c, json={"data": [{"b64_json": PNG}]} if c == 200 else {"error": "slow"})

    p = OpenAIImageProvider("k", "m", "https://x", transport=httpx.MockTransport(handler))
    assert p.generate("a")
    p2 = OpenAIImageProvider("k", "m", "https://x", transport=httpx.MockTransport(lambda r: httpx.Response(400, text="bad")))
    with pytest.raises(ProviderError):
        p2.generate("a")


def test_gemini_generate():
    def handler(req: httpx.Request):
        body = json.loads(req.content)
        assert body["generationConfig"]["responseModalities"] == ["IMAGE"]
        assert len(body["contents"][0]["parts"]) == 2  # text + reference
        assert req.headers["x-goog-api-key"] == "g"
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": PNG}}]}}]})

    p = GeminiImageProvider("g", "gem", "https://g.example.com", transport=httpx.MockTransport(handler))
    assert p.generate("dog", (2550, 3300), reference_images=[base64.b64decode(PNG)])[:4] == b"\x89PNG"
    assert GeminiImageProvider.aspect_ratio((2550, 3300)) == "3:4"


def test_missing_keys_raise():
    with pytest.raises(ProviderError):
        OpenAIImageProvider("", "m", "https://x")


class FakeMessages:
    def __init__(self, text):
        self.text = text
        self.kwargs = None

    def create(self, **kw):
        self.kwargs = kw
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


def test_anthropic_adapter_json_and_cost():
    recs = []
    base.add_usage_sink(recs.append)
    fake = SimpleNamespace(messages=FakeMessages('{"title": "x"}'))
    llm = AnthropicLLM("", "claude-opus-5-5", client=fake)
    out = llm.analyze([base64.b64decode(PNG)], "describe", {"type": "object"})
    assert out == {"title": "x"}
    content = fake.messages.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image" and content[0]["source"]["media_type"] == "image/png"
    assert fake.messages.kwargs["model"] == "claude-opus-5-5"
    assert recs[0].est_cost_usd == pytest.approx((1000 * 4 + 200 * 20) / 1e6)
