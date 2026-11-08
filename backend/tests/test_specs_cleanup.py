import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.providers.mock import MockImageProvider
from app.services import cleanup, specs


@pytest.mark.parametrize("trim,bleed,px", [
    ("8.5x11in", False, (2550, 3300)),
    ("8.5x11in", True, (2625, 3375)),
    ("6x9in", False, (1800, 2700)),
    ("A4", False, (2480, 3508)),
])
def test_pixel_sizes(trim, bleed, px):
    assert specs.page_spec(trim, bleed).pixel_size == px


def test_points_with_bleed():
    sp = specs.page_spec("8.5x11in", True)
    assert sp.points == pytest.approx((630.0, 810.0))


def test_custom_trim_and_errors():
    assert specs.trim_inches("200x250mm") == pytest.approx((200 / 25.4, 250 / 25.4))
    with pytest.raises(specs.SpecError):
        specs.trim_inches("huge")
    with pytest.raises(specs.SpecError):
        specs.trim_inches("50x50in")


def test_cleanup_output_size_dpi_and_pure_bw(tmp_path):
    sp = specs.page_spec("8.5x11in", True)
    raw = MockImageProvider().generate("a bear", (1024, 1024))
    img = cleanup.clean_line_art(raw, sp)
    assert img.size == sp.pixel_size
    assert set(np.unique(np.asarray(img)).tolist()) <= {0, 255}
    out = cleanup.save_print_png(img, tmp_path / "p.png")
    with Image.open(out) as im:
        assert im.size == (2625, 3375)
        assert tuple(round(v) for v in im.info["dpi"]) == (300, 300)
        assert im.mode == "1"


def test_cleanup_keeps_safe_margin():
    sp = specs.page_spec("8.5x11in", False)
    im = Image.new("L", (800, 800), 255)
    ImageDraw.Draw(im).rectangle([0, 0, 799, 799], outline=0, width=10)  # touches every edge
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    out = np.asarray(cleanup.clean_line_art(buf.getvalue(), sp))
    margin = sp.safe_margin_px
    assert (out[:margin - 2, :] == 255).all() and (out[-(margin - 2):, :] == 255).all()
    assert (out[:, :margin - 2] == 255).all() and (out[:, -(margin - 2):] == 255).all()


def test_cleanup_removes_grey_and_specks():
    sp = specs.page_spec("6x9in", False)
    im = Image.new("L", (600, 900), 255)
    d = ImageDraw.Draw(im)
    d.ellipse([150, 200, 450, 600], outline=0, width=8)
    d.rectangle([200, 300, 260, 360], fill=200)  # light grey fill -> white
    d.point([(50, 50)], fill=0)  # isolated speck
    out = cleanup.clean_line_art(im, sp)
    arr = np.asarray(out)
    assert set(np.unique(arr).tolist()) <= {0, 255}
    assert arr.mean() > 200
