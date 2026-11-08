from pathlib import Path

import httpx
import pytest

from app.services import url_fetch
from app.services.url_fetch import FetchBlocked, fetch_page, parse_html, validate_url

FIX = Path(__file__).parent / "fixtures"


def public(_host):
    return ["93.184.216.34"]


@pytest.mark.parametrize("url", [
    "ftp://example.com/x", "file:///etc/passwd", "http://localhost/", "http://127.0.0.1/", "http://10.0.0.5/",
    "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data", "http://[::1]/", "http://0.0.0.0/",
    "http://100.64.1.1/", "http://user:pw@example.com/", "http://printer.local/", "http://[::ffff:127.0.0.1]/",
])
def test_ssrf_blocks(url):
    with pytest.raises(FetchBlocked):
        validate_url(url, resolver=public)


def test_ssrf_blocks_private_dns_resolution():
    with pytest.raises(FetchBlocked):
        validate_url("https://evil.example.com/", resolver=lambda h: ["93.184.216.34", "10.1.2.3"])


def test_public_allowed():
    assert validate_url("https://www.example.com/book", resolver=public)


def test_parse_store_page():
    info = parse_html((FIX / "store_page.html").read_text(), "https://shop.example.com/item/1")
    assert "cozy bakery scenes" in info.description
    assert info.product["name"].startswith("Bramble")
    assert info.image_urls[0] == "https://images.example.com/cover.jpg"
    assert "https://shop.example.com/p2.jpg" in info.image_urls
    assert all("icon.png" not in u for u in info.image_urls)
    assert len(info.image_urls) <= url_fetch.MAX_IMAGES
    assert any("Sunnyday" in t for t in info.brand_terms)
    assert not info.is_thin


def test_thin_page():
    info = parse_html((FIX / "thin_page.html").read_text(), "https://shop.example.com/x")
    assert info.is_thin


def test_fetch_with_redirect_to_private_is_blocked(monkeypatch):
    def handler(request: httpx.Request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    with pytest.raises(FetchBlocked):
        fetch_page("https://shop.example.com/", resolver=public, transport=httpx.MockTransport(handler))


def test_fetch_ok_and_size_cap(monkeypatch):
    html = (FIX / "store_page.html").read_text()

    def handler(request: httpx.Request):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    info = fetch_page("https://shop.example.com/", resolver=public, transport=httpx.MockTransport(handler))
    assert info.title.startswith("Bramble")
    monkeypatch.setattr(url_fetch, "MAX_HTML_BYTES", 100)
    with pytest.raises(url_fetch.FetchFailed):
        fetch_page("https://shop.example.com/", resolver=public, transport=httpx.MockTransport(handler))
