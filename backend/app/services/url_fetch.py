"""Store-page fetcher with SSRF guard (PLAN.md section 17).

- only http/https, default ports or explicit ports > 0
- hostname resolved; every resolved IP must be public (no private, loopback,
  link-local, multicast, reserved, unspecified, CGNAT/shared)
- redirects followed manually (max 5), each hop re-validated
- size and time limits; cookies live only inside one fetch (some shops need them to serve the page)
- sends browser-like headers and retries once with a mobile user agent when a shop answers with a bot wall
"""

from __future__ import annotations

import ipaddress
import json
import re
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
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1",
]
USER_AGENT = USER_AGENTS[0]
THIN_TEXT_CHARS = 80
BODY_TEXT_CHARS = 3000
BOT_WALL_MARKERS = (
    "enter the characters you see below", "api-services-support@amazon", "robot check", "are you a human",
    "verify you are human", "unusual traffic", "access denied", "just a moment...", "captcha",
)

Resolver = Callable[[str], list[str]]


class FetchBlocked(ValueError):
    """URL rejected by the SSRF guard."""


class FetchFailed(RuntimeError):
    pass


class SiteBlocked(FetchFailed):
    """The shop answered with a bot wall / captcha instead of the product page."""


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


def _headers(accept: str, user_agent: str) -> dict[str, str]:
    return {"User-Agent": user_agent, "Accept": accept, "Accept-Language": "en-US,en;q=0.9",
            "Upgrade-Insecure-Requests": "1"}


def _get(url: str, max_bytes: int, resolver: Resolver, transport: httpx.BaseTransport | None,
         accept: str, user_agent: str = USER_AGENT) -> tuple[str, bytes, str]:
    current = url
    # One client per fetch: cookies set on the first hop are sent on the following redirects.
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, transport=transport,
                      headers=_headers(accept, user_agent)) as client:
        for _ in range(MAX_REDIRECTS + 1):
            validate_url(current, resolver)
            with client.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("location")
                    if not loc:
                        raise FetchFailed("redirect without location")
                    current = urljoin(current, loc)
                    continue
                if r.status_code in (403, 429, 503):
                    raise SiteBlocked(f"{urlparse(current).hostname} refused the request (HTTP {r.status_code})")
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
    body_text: str = ""

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
    def is_text_thin(self) -> bool:
        """No real description was read (pictures alone are a weak basis for the concept)."""
        desc = self.description.strip() or str(self.product.get("description", "") or "")
        readable = 0 if is_boilerplate_description(desc) else len(desc)
        return readable < THIN_TEXT_CHARS and len(self.body_text) < 3 * THIN_TEXT_CHARS

    @property
    def is_thin(self) -> bool:
        desc = self.description.strip() or str(self.product.get("description", "") or "")
        readable = 0 if is_boilerplate_description(desc) else len(desc)
        return readable < THIN_TEXT_CHARS and len(self.body_text) < 3 * THIN_TEXT_CHARS and not self.image_urls

    def as_dict(self) -> dict[str, Any]:
        return {"url": self.url, "title": self.title, "description": self.description, "og": self.og,
                "product": self.product, "image_urls": self.image_urls, "body_text": self.body_text,
                "thin": self.is_thin}


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
    if is_amazon(base_url):
        _parse_amazon(soup, info)
    if len(info.description.strip()) < THIN_TEXT_CHARS:
        info.body_text = _visible_text(soup)
    return info


AMAZON_UI_NOISE = re.compile(r"Brief content visible, double tap to read full content\.|"
                             r"Full content visible, double tap to read brief content\.|Read more|Read less", re.I)
BOILERPLATE_DESC = re.compile(r"on Amazon\.[a-z.]+\.?\s*\*?FREE\*? shipping|free shipping on qualifying offers", re.I)


def is_boilerplate_description(text: str) -> bool:
    return bool(BOILERPLATE_DESC.search(text or ""))


AMAZON_SIZE_TOKEN = re.compile(r"\._[A-Z0-9_,\-]+_(?=\.(?:jpe?g|png|webp)$)", re.I)


def is_amazon(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == "amazon.com" or host.startswith("amazon.") or ".amazon." in host or host in ("a.co", "amzn.to")


def amazon_asin(url: str) -> str | None:
    m = re.search(r"/(?:dp|gp/product|gp/aw/d|product)/([A-Z0-9]{10})(?:[/?#]|$)", urlparse(url).path + "/", re.I)
    return m.group(1).upper() if m else None


def canonical_url(url: str) -> str:
    """Amazon product links carry tracking junk and slugs; the short /dp/ form is the most reliable."""
    p = urlparse(url.strip())
    asin = amazon_asin(p.geturl()) if is_amazon(url) else None
    if asin and p.hostname:
        return f"https://{p.hostname}/dp/{asin}"
    return url.strip()


def url_hint_words(url: str) -> str:
    """Human words from the link slug (Amazon/Etsy slugs usually contain the title)."""
    path = urlparse(url).path
    seg = max((x for x in path.split("/") if re.search(r"[A-Za-z]{3}", x)), key=len, default="")
    words = [w for w in re.split(r"[-_+%\d]+", seg) if len(w) > 1]
    return " ".join(words) if len(words) >= 2 else ""


def _visible_text(soup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        tag.decompose()
    seen: list[str] = []
    total = 0
    for el in soup.find_all(["h1", "h2", "h3", "p", "li"]):
        t = " ".join(el.get_text(" ", strip=True).split())
        if len(t) < 25 or t in seen:
            continue
        seen.append(t)
        total += len(t)
        if total >= BODY_TEXT_CHARS:
            break
    return "\n".join(seen)[:BODY_TEXT_CHARS]


def _parse_amazon(soup, info: PageInfo) -> None:
    title = soup.select_one("#productTitle") or soup.select_one("#title")
    if title and title.get_text(strip=True):
        info.title = " ".join(title.get_text(" ", strip=True).split())
        info.brand_terms.append(info.title)
    byline = soup.select_one("#bylineInfo")
    if byline:
        info.brand_terms.append(" ".join(byline.get_text(" ", strip=True).split()))
    parts: list[str] = []
    for sel in ("#bookDescription_feature_div", "#productDescription", "#productDescription_feature_div",
                "#drengr_MobileTabbedDescriptionOverviewContent_feature_div", "#drengr_mobileTabbedDescription_feature_div",
                "#feature-bullets", "#editorialReviews_feature_div", "#detailBullets_feature_div",
                "#featureBulletsAndDetailBullets_feature_div"):
        for node in soup.select(sel):
            txt = AMAZON_UI_NOISE.sub(" ", " ".join(node.get_text(" ", strip=True).split())).strip()
            if len(txt) > 20 and not any(txt in p or p in txt for p in parts):
                parts.append(txt)
    if parts:
        info.description = "\n".join(parts)[:4000]
    elif is_boilerplate_description(info.description):
        info.description = ""  # Amazon's stock meta blurb ("... on Amazon.com. *FREE* shipping ...") says nothing
    urls: list[str] = []
    for img in soup.select("#landingImage, #imgBlkFront, #ebooksImgBlkFront, #main-image"):
        dyn = img.get("data-a-dynamic-image")
        if dyn:
            try:
                sizes = json.loads(dyn)
                urls += sorted(sizes, key=lambda u: -int(sizes[u][0]))
            except (json.JSONDecodeError, TypeError, IndexError, ValueError):
                pass
        for attr in ("data-old-hires", "src"):
            if img.get(attr):
                urls.append(img[attr])
    for img in soup.select("#altImages img, #imageBlock img"):
        src = img.get("src") or ""
        if "images/I/" in src:
            urls.append(src)
    big: list[str] = []
    for u in urls + list(info.image_urls):
        u = AMAZON_SIZE_TOKEN.sub("", u)  # drop the ._AC_US40_ thumbnail token -> full size
        if "images/I/" in u and u not in big and "sprite" not in u and not u.lower().endswith(".svg"):
            big.append(u)
    if big:
        info.image_urls = big[:MAX_IMAGES]


def looks_like_bot_wall(html: str) -> bool:
    head = html[:6000].lower()
    if not any(m in head for m in BOT_WALL_MARKERS):
        return False
    # a real product page that merely mentions a marker is long and has product markup
    return "productTitle" not in html and "application/ld+json" not in html and len(html) < 60000


def fetch_page(url: str, *, resolver: Resolver = default_resolver,
               transport: httpx.BaseTransport | None = None) -> PageInfo:
    """Fetch and parse a store page. Tries a desktop and then a mobile browser identity; raises SiteBlocked when
    the shop keeps answering with a captcha / bot wall."""
    target = canonical_url(url)
    last: Exception | None = None
    for ua in USER_AGENTS:
        try:
            final, body, ctype = _get(target, MAX_HTML_BYTES, resolver, transport, "text/html,application/xhtml+xml",
                                      user_agent=ua)
        except SiteBlocked as e:
            last = e
            continue
        if ctype and "html" not in ctype and "xml" not in ctype:
            raise FetchFailed(f"not an HTML page ({ctype})")
        html = body.decode("utf-8", errors="replace")
        if looks_like_bot_wall(html):
            last = SiteBlocked(f"{urlparse(final).hostname} showed a robot check instead of the page")
            continue
        if is_amazon(final) and "productTitle" not in html:
            # Amazon answers some browser identities with a tiny stub without product data; try the next one.
            last = SiteBlocked(f"{urlparse(final).hostname} returned an empty product page")
            continue
        info = parse_html(html, final)
        info.url = url.strip()
        return info
    raise last or SiteBlocked("the shop blocked the request")


def fetch_image(url: str, *, resolver: Resolver = default_resolver,
                transport: httpx.BaseTransport | None = None) -> bytes:
    _, body, ctype = _get(url, MAX_IMAGE_BYTES, resolver, transport, "image/*")
    if ctype and not ctype.startswith("image/"):
        raise FetchFailed("not an image")
    return body
