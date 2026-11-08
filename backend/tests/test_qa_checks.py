from PIL import Image, ImageDraw

from app.providers.mock import MockImageProvider
from app.services import qa_checks


def test_mock_art_passes():
    for i in range(10):
        r = qa_checks.analyze(MockImageProvider().generate(f"page {i}", (2550, 3300)))
        assert r["pass"], r


def test_shading_detected():
    im = Image.new("L", (600, 800), 255)
    d = ImageDraw.Draw(im)
    d.ellipse([100, 100, 500, 600], outline=0, width=6)
    d.rectangle([150, 250, 450, 500], fill=140)
    r = qa_checks.analyze(im)
    assert not r["pass"]
    assert any("grey" in i for i in r["issues"])


def test_edge_touch_detected():
    im = Image.new("L", (500, 600), 255)
    ImageDraw.Draw(im).ellipse([-60, 100, 300, 400], outline=0, width=6)
    r = qa_checks.analyze(im)
    assert any("edge" in i for i in r["issues"])


def test_empty_and_too_dark():
    assert any("empty" in i for i in qa_checks.analyze(Image.new("L", (300, 300), 255))["issues"])
    dark = Image.new("L", (300, 300), 255)
    ImageDraw.Draw(dark).rectangle([30, 30, 270, 270], fill=0)
    assert any("black" in i for i in qa_checks.analyze(dark)["issues"])
