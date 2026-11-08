"""Line-art cleanup (PLAN.md section 12):
grayscale -> upscale to target -> threshold to pure B/W -> despeckle ->
fit on the page canvas with a safe margin -> PNG with 300 DPI metadata."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from .specs import PageSpec


def to_gray(data: bytes | Image.Image) -> Image.Image:
    img = data if isinstance(data, Image.Image) else Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        img = bg
    return img.convert("L")


def otsu_threshold(gray: np.ndarray) -> int:
    hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = gray.size
    sum_all = np.dot(np.arange(256), hist)
    w_b = 0.0
    sum_b = 0.0
    best, best_t = -1.0, 128
    for t in range(256):
        w_b += hist[t]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * hist[t]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best, best_t = between, t
    # bias toward keeping thin lines dark, but never above 200
    return int(min(200, max(90, best_t)))


def threshold(img: Image.Image, t: int | None = None) -> Image.Image:
    arr = np.asarray(img.convert("L"))
    t = otsu_threshold(arr) if t is None else t
    out = np.where(arr <= t, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "L")


def despeckle(img: Image.Image, size: int = 3) -> Image.Image:
    """Remove isolated specks: median filter on B/W, then re-threshold."""
    return threshold(img.filter(ImageFilter.MedianFilter(size)), 128)


def content_bbox(img: Image.Image) -> tuple[int, int, int, int] | None:
    inv = ImageOps.invert(img.convert("L"))
    return inv.getbbox()


def fit_on_canvas(img: Image.Image, spec: PageSpec) -> Image.Image:
    W, H = spec.pixel_size
    margin = spec.safe_margin_px
    canvas = Image.new("L", (W, H), 255)
    bbox = content_bbox(img)
    if bbox is None:
        return canvas
    art = img.crop(bbox)
    max_w, max_h = W - 2 * margin, H - 2 * margin
    scale = min(max_w / art.width, max_h / art.height)
    new = (max(1, int(art.width * scale)), max(1, int(art.height * scale)))
    art = art.resize(new, Image.LANCZOS)
    canvas.paste(art, ((W - new[0]) // 2, (H - new[1]) // 2))
    return canvas


def clean_line_art(data: bytes | Image.Image, spec: PageSpec) -> Image.Image:
    gray = to_gray(data)
    W, H = spec.pixel_size
    # upscale (smoothly) so the subject fills the printable area before threshold
    bbox = content_bbox(threshold(gray))
    if bbox:
        gray = gray.crop(bbox)
    max_w, max_h = W - 2 * spec.safe_margin_px, H - 2 * spec.safe_margin_px
    scale = min(max_w / gray.width, max_h / gray.height)
    if scale > 1.0:
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)
    bw = despeckle(threshold(gray))
    final = fit_on_canvas(bw, spec)
    return threshold(final, 128)  # resampling in fit -> re-binarize


def save_print_png(img: Image.Image, path: Path, dpi: int = 300) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("1").save(path, format="PNG", dpi=(dpi, dpi), optimize=True)
    return path


def make_thumbnail(src: Path, dest: Path, max_side: int = 360) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("L")
        im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(dest, format="PNG", optimize=True)
    return dest
