"""HTML -> PDF (WeasyPrint) -> PNG (pypdfium2) for code-drawn pages."""

from __future__ import annotations

import threading
from pathlib import Path

from PIL import Image

# WeasyPrint (Pango/fontconfig via cffi) and pypdfium2 are not thread-safe.
# Page generation runs in a thread pool, so every native PDF call goes
# through this process-wide lock.
PDF_LOCK = threading.RLock()


def html_to_pdf_bytes(html: str, base_url: str | None = None) -> bytes:
    from weasyprint import HTML  # lazy import (system libs: pango)

    with PDF_LOCK:
        return HTML(string=html, base_url=base_url or str(Path.cwd())).write_pdf()


def pdf_page_to_image(pdf: bytes, page_index: int = 0, dpi: int = 300) -> Image.Image:
    import pypdfium2 as pdfium

    with PDF_LOCK:
        doc = pdfium.PdfDocument(pdf)
        try:
            page = doc[page_index]
            bitmap = page.render(scale=dpi / 72)
            img = bitmap.to_pil().convert("L")
            page.close()
            return img
        finally:
            doc.close()


def pdf_to_images(pdf: bytes, max_pages: int = 15, dpi: int = 110) -> list[Image.Image]:
    import pypdfium2 as pdfium

    with PDF_LOCK:
        doc = pdfium.PdfDocument(pdf)
        try:
            return [doc[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(min(len(doc), max_pages))]
        finally:
            doc.close()


def render_html_page_png(html: str, out: Path, size_px: tuple[int, int], dpi: int = 300) -> Path:
    pdf = html_to_pdf_bytes(html)
    img = pdf_page_to_image(pdf, 0, dpi)
    if img.size != size_px:
        img = img.resize(size_px, Image.LANCZOS)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, format="PNG", dpi=(dpi, dpi), optimize=True)
    return out
