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


def _html_handler(html, seen=None):
    def handler(request: httpx.Request):
        if seen is not None:
            seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    return handler


def test_amazon_page_is_parsed():
    info = parse_html((FIX / "amazon_page.html").read_text(), "https://www.amazon.com/dp/B0TESTASIN")
    assert info.title == "Wobble Pond Friends Coloring Book"
    assert "gentle pond animals" in info.description
    assert info.image_urls[0] == "https://m.media-amazon.com/images/I/81big.jpg"  # biggest first, size token stripped
    assert all("._" not in u for u in info.image_urls)
    assert not info.is_thin
    assert any("Wobble" in t for t in info.brand_terms)


def test_amazon_url_is_canonicalized():
    long = "https://www.amazon.com/Wobble-Pond-Friends-Coloring-Book/dp/B0TESTASIN/ref=sr_1_3?crid=XYZ&keywords=a"
    assert url_fetch.canonical_url(long) == "https://www.amazon.com/dp/B0TESTASIN"
    assert url_fetch.canonical_url("https://shop.example.com/x?y=1") == "https://shop.example.com/x?y=1"
    assert url_fetch.url_hint_words(long) in ("Wobble Pond Friends Coloring Book",) or "Wobble" in url_fetch.url_hint_words(long)


def test_browser_headers_and_canonical_target():
    seen: list[httpx.Request] = []
    html = (FIX / "amazon_page.html").read_text()
    fetch_page("https://www.amazon.com/Wobble-Pond/dp/B0TESTASIN/ref=x?tag=1", resolver=public,
               transport=httpx.MockTransport(_html_handler(html, seen)))
    assert str(seen[0].url) == "https://www.amazon.com/dp/B0TESTASIN"
    assert "Chrome" in seen[0].headers["user-agent"] and "en-US" in seen[0].headers["accept-language"]


def test_bot_wall_retries_with_mobile_agent_then_succeeds():
    agents: list[str] = []
    good = (FIX / "amazon_page.html").read_text()
    wall = (FIX / "thin_page.html").read_text()

    def handler(request: httpx.Request):
        agents.append(request.headers["user-agent"])
        return httpx.Response(200, headers={"content-type": "text/html"}, text=wall if len(agents) == 1 else good)

    info = fetch_page("https://www.amazon.com/dp/B0TESTASIN", resolver=public, transport=httpx.MockTransport(handler))
    assert info.title.startswith("Wobble") and len(agents) == 2 and "iPhone" in agents[1]


def test_persistent_bot_wall_raises_site_blocked():
    wall = (FIX / "thin_page.html").read_text()
    with pytest.raises(url_fetch.SiteBlocked):
        fetch_page("https://www.amazon.com/dp/B0TESTASIN", resolver=public,
                   transport=httpx.MockTransport(_html_handler(wall)))
    with pytest.raises(url_fetch.SiteBlocked):
        fetch_page("https://www.amazon.com/dp/B0TESTASIN", resolver=public,
                   transport=httpx.MockTransport(lambda r: httpx.Response(503)))


def test_body_text_fallback_for_pages_without_meta():
    html = ("<html><body><h1>Dinosaur Dig Activity Book</h1><p>Dig through twenty pages of fossil mazes and bone counting games.</p>"
            "<p>Big friendly dinosaurs, thick outlines and plenty of room to color for curious young explorers.</p>"
            "<p>Each page has a small challenge so children can play, count and color at their own pace.</p></body></html>")
    info = parse_html(html, "https://shop.example.com/dino")
    assert "fossil mazes" in info.body_text and not info.is_thin


STUB = "<html><head><title>The Big Book of WHY?</title><meta name=\"description\" content=\"The Big Book of WHY? [Ahmed] on Amazon.com. *FREE* shipping on qualifying offers.\"></head><body></body></html>"
MOBILE = ("<html><body><span id=\"productTitle\">The Big Book of WHY?</span>"
          "<div id=\"drengr_mobileTabbedDescription_feature_div\">Brief content visible, double tap to read full content. "
          "Book overview 50 fascinating questions about animals, space and the human body for curious kids ages 8-12.</div>"
          "</body></html>")


def test_amazon_stub_is_skipped_and_mobile_page_read():
    agents: list[str] = []

    def handler(request: httpx.Request):
        agents.append(request.headers["user-agent"])
        return httpx.Response(200, headers={"content-type": "text/html"}, text=STUB if len(agents) == 1 else MOBILE)

    info = fetch_page("https://www.amazon.com/dp/B0HR19V6T5", resolver=public, transport=httpx.MockTransport(handler))
    assert len(agents) == 2 and "iPhone" in agents[1]
    assert "50 fascinating questions" in info.description and "double tap" not in info.description
    assert not info.is_text_thin


def test_boilerplate_amazon_blurb_counts_as_thin():
    info = parse_html(STUB, "https://shop.example.com/x")
    assert info.is_text_thin
