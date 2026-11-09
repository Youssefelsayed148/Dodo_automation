"""Upload validation: type, size, decode check. PDFs -> up to 15 page images."""

from __future__ import annotations

import io

from PIL import Image

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PDF_BYTES = 40 * 1024 * 1024
MAX_PDF_PAGES = 15
MAX_FILES = 20
IMAGE_TYPES = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}


class UploadError(ValueError):
    pass


def sniff(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def validate_image(data: bytes, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[bytes, str]:
    if len(data) > max_bytes:
        raise UploadError(f"image is larger than {max_bytes // (1024 * 1024)} MB")
    kind = sniff(data)
    if kind not in ("png", "jpg", "webp"):
        raise UploadError("only PNG, JPEG, WEBP images or PDF files are accepted")
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            if im.width * im.height > 60_000_000:
                raise UploadError("image dimensions too large")
    except UploadError:
        raise
    except Exception as e:
        raise UploadError(f"image could not be decoded: {e}") from e
    return data, kind


def pdf_to_page_images(data: bytes, max_pages: int = MAX_PDF_PAGES) -> list[bytes]:
    if len(data) > MAX_PDF_BYTES:
        raise UploadError("PDF is larger than 40 MB")
    if sniff(data) != "pdf":
        raise UploadError("not a PDF file")
    from ..render.raster import pdf_to_images

    try:
        images = pdf_to_images(data, max_pages=max_pages)
    except Exception as e:
        raise UploadError(f"PDF could not be read: {e}") from e
    out = []
    for im in images:
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
        out.append(buf.getvalue())
    return out


def process_upload(data: bytes) -> list[tuple[bytes, str]]:
    """Return list of (bytes, ext) images for one uploaded file."""
    kind = sniff(data)
    if kind == "pdf":
        return [(b, "jpg") for b in pdf_to_page_images(data)]
    return [validate_image(data)]
