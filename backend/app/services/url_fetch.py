"""Store-page fetcher with SSRF guard (PLAN.md section 17).

- only http/https, default ports or explicit ports > 0
- hostname resolved; every resolved IP must be public (no private, loopback,
  link-local, multicast, reserved, unspecified, CGNAT/shared)
- redirects followed manually (max 5), each hop re-validated
- size and time limits, no cookies
"""

from __future__ import annotations

import ipaddress
import json
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

MAX_HTML_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGES = 5
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; DodoBookStudio/1.0; personal use)"
THIN_TEXT_CHARS = 80

Resolver = Callable[[str], list[str]]


class FetchBlocked(ValueError):
    """URL rejected by the SSRF guard."""


class FetchFailed(RuntimeError):
    pass


def default_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchFailed(f"could not resolve host '{host}'") from e
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved
            or addr.is_unspecified):
        return False
    if isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"):
        return False
    return addr.is_global


def validate_url(url: str, resolver: Resolver = default_resolver) -> str:
    try:
        p = urlparse(url.strip())
    except ValueError as e:
        raise FetchBlocked(f"invalid URL: {e}") from e
    if p.scheme not in ("http", "https"):
        raise FetchBlocked("only http and https links are allowed")
    if not p.hostname:
        raise FetchBlocked("URL has no host")
    if p.username or p.password:
        raise FetchBlocked("URLs with credentials are not allowed")
    host = p.hostname.strip("[]").lower()
    if host in ("localhost",) or host.endswith(".localhost") or host.endswith(".local") or host.endswith(".internal"):
        raise FetchBlocked("local hostnames are not allowed")
    try:
        _ = p.port
    except ValueError as e:
        raise FetchBlocked("invalid port") from e
    # literal IP?
    try:
        ipaddress.ip_address(host)
        ips = [host]
    except ValueError:
        ips = resolver(host)
    if not ips:
        raise FetchFailed(f"host '{host}' did not resolve")
    for ip in ips:
        if not is_public_ip(ip):
            raise FetchBlocked(f"host '{host}' resolves to a non-public address")
    return url.strip()


def _get(url: str, max_bytes: int, resolver: Resolver, transport: httpx.BaseTransport | None,
         accept: str) -> tuple[str, bytes, str]:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(current, resolver)
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False, transport=transport,
                          headers={"User-Agent": USER_AGENT, "Accept": accept}) as client:
            with client.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise FetchFailed("redirect without location")
                    current = urljoin(current, loc)
                    continue
                if r.status_code >= 400:
                    raise FetchFailed(f"HTTP {r.status_code} from {urlparse(current).hostname}")
                declared = r.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    raise FetchFailed("response too large")
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise FetchFailed("response too large")
                return current, bytes(buf), r.headers.get("content-type", "")
    raise FetchFailed("too many redirects")


@dataclass
class PageInfo:
    url: str
    title: str = ""
    description: str = ""
    og: dict[str, str] = field(default_factory=dict)
    product: dict[str, Any] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)
    brand_terms: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        parts = [self.title, self.description, self.og.get("title", ""), self.og.get("description", ""),
                 str(self.product.get("name", "")), str(self.product.get("description", ""))]
        seen: list[str] = []
        for p in parts:
            p = (p or "").strip()
            if p and p not in seen:
                seen.append(p)
        return "\n".join(seen)

    @property
    def is_thin(self) -> bool:
        return len(self.description.strip() or self.product.get("description", "") or "") < THIN_TEXT_CHARS and not self.image_urls

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "title": self.title, "description": self.description, "og": self.og,
                "product": self.product, "image_urls": self.image_urls, "thin": self.is_thin}


def _iter_jsonld(obj: Any):
    if isinstance(obj, list):
        for o in obj:
            yield from _iter_jsonld(o)
    elif isinstance(obj, dict):
        yield obj
        if "@graph" in obj:
            yield from _iter_jsonld(obj["@graph"])


def parse_html(html: str, base_url: str) -> PageInfo:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    info = PageInfo(url=base_url)
    if soup.title and soup.title.string:
        info.title = soup.title.string.strip()
    for m in soup.find_all("meta"):
        prop = (m.get("property") or m.get("name") or "").lower()
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if prop == "description" and not info.description:
            info.description = content
        elif prop.startswith("og:"):
            info.og.setdefault(prop[3:], content)
        elif prop in ("twitter:image",) and "image" not in info.og:
            info.og["image"] = content
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or s.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_jsonld(data):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(x in ("Product", "Book") for x in types):
                info.product = {k: node.get(k) for k in ("name", "description", "image", "brand", "author") if node.get(k)}
                break
    if not info.description:
        info.description = info.og.get("description") or str(info.product.get("description") or "")
    # brand / title terms used for the originality scrub
    terms: list[str] = []
    for v in (info.product.get("brand"), info.product.get("author")):
        if isinstance(v, dict):
            v = v.get("name")
        if isinstance(v, list):
            v = " ".join(str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in v)
        if v:
            terms.append(str(v))
    for t in (info.title, info.og.get("title"), info.product.get("name")):
        if t:
            terms.append(str(t))
    info.brand_terms = terms
    # images: og, json-ld, then big <img>
    urls: list[str] = []
    if info.og.get("image"):
        urls.append(info.og["image"])
    img = info.product.get("image")
    for u in (img if isinstance(img, list) else [img] if img else []):
        if isinstance(u, dict):
            u = u.get("url") or u.get("contentUrl")
        if u:
            urls.append(str(u))
    for tag in soup.find_all("img"):
        src = tag.get("data-old-hires") or tag.get("data-src") or tag.get("src") or ""
        if not src or src.startswith("data:") or src.endswith(".svg"):
            continue
        try:
            w = int(tag.get("width") or 0)
        except ValueError:
            w = 0
        if w and w < 200:
            continue
        urls.append(src)
    clean: list[str] = []
    for u in urls:
        full = urljoin(base_url, u)
        if full.startswith(("http://", "https://")) and full not in clean:
            clean.append(full)
    info.image_urls = clean[:MAX_IMAGES]
    return info


def fetch_page(url: str, *, resolver: Resolver = default_resolver,
               transport: httpx.BaseTransport | None = None) -> PageInfo:
    final, body, ctype = _get(url, MAX_HTML_BYTES, resolver, transport, "text/html,application/xhtml+xml")
    if ctype and "html" not in ctype and "xml" not in ctype:
        raise FetchFailed(f"not an HTML page ({ctype})")
    html = body.decode("utf-8", errors="replace")
    return parse_html(html, final)


def fetch_image(url: str, *, resolver: Resolver = default_resolver,
                transport: httpx.BaseTransport | None = None) -> bytes:
    _, body, ctype = _get(url, MAX_IMAGE_BYTES, resolver, transport, "image/*")
    if ctype and not ctype.startswith("image/"):
        raise FetchFailed("not an image")
    return body
