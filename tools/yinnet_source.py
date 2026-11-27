"""Read-only inventory reader for YINNET Singapore VPS ①.

Only the official public Singapore VPS catalogue is requested. Product links
are inspected as text but never followed; no cart, configuration, login, or
order endpoint is requested.
"""

from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


LISTING_URL = "https://www.yin-net.com/index.php?rp=/store/sgvps"
PRODUCT_ROUTE = "/store/sgvps/sgvps1"
PRODUCT_NAME = "新加坡 | VPS ①"
REGION = "Singapore"
SOURCE_KEY = "yinnet-" + "sg-1"
MAX_RESPONSE_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 15

_PLAN_RE = re.compile(r"新加坡\s*[|｜]\s*VPS\s*([①②③④])")
_PRICE_RE = re.compile(
    r"(?:起\s*)?\$\s*(\d+(?:\.\d{1,2})?)\s*USD\s*"
    r"(?:月繳|月缴|月付|月租|每月|monthly|per\s+month|/\s*month)",
    re.IGNORECASE,
)
_QUANTITY_RE = re.compile(r"(?<!\w)(\d+)\s*可用")
_OUT_OF_STOCK = ("缺貨", "缺货", "售罄", "已售完", "沒有貨", "没有货",
                 "不可購買", "不可购买", "not in stock", "out of stock", "sold out")
_IN_STOCK = ("有貨", "有货", "可購買", "可购买", "in stock", "available now")
_CHALLENGE_MARKERS = (
    "please enable cookies",
    "captcha",
    "checking your browser",
    "verify you are human",
    "cloudflare ray id",
    "sorry, you have been blocked",
    "attention required! | cloudflare",
    "access denied",
    "challenge-platform",
)


def _is_listing_url(url: str) -> bool:
    """Return true only for the public catalogue route, never checkout pages."""
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    return (
        parsed.scheme == "https"
        and parsed.hostname == "www.yin-net.com"
        and parsed.path == "/index.php"
        and query.get("rp") == ["/store/sgvps"]
    )


class _ListingOnlyRedirects(HTTPRedirectHandler):
    """Allow redirects only when they stay on this exact public listing."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        target = urljoin(req.full_url, newurl)
        if _is_listing_url(target):
            return super().redirect_request(req, fp, code, msg, headers, target)
        return None


class _VisibleText(HTMLParser):
    """Extract ordinary page text while ignoring scripts and styles."""

    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            if tag in self._SKIP_TAGS:
                self._skip_depth += 1
            return
        if tag in self._SKIP_TAGS:
            self._skip_depth = 1
            return
        self.parts.append(" ")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self._skip_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            if tag in self._SKIP_TAGS:
                self._skip_depth -= 1
            return
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


class _Links(HTMLParser):
    """Collect anchors only to confirm the intended SKU link exists."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(urljoin(LISTING_URL, href))


def _unknown() -> dict[str, Any]:
    return {
        "name": PRODUCT_NAME,
        "available": None,
        "price": None,
        "quantity": None,
        "region": REGION,
        "url": LISTING_URL,
    }


def _fetch_html(timeout: float = REQUEST_TIMEOUT_SECONDS) -> str:
    """Fetch only the official public product list with the standard library."""
    if not _is_listing_url(LISTING_URL):
        raise ValueError("unsafe listing URL")

    request = Request(
        LISTING_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "vps-stock-opencli/1.0 read-only public inventory check",
        },
        method="GET",
    )
    opener = build_opener(_ListingOnlyRedirects())
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        if not _is_listing_url(final_url):
            raise ValueError("redirect left the public listing")
        if response.headers.get_content_type() != "text/html":
            raise ValueError("listing did not return HTML")

        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("listing response exceeded size limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="strict")


def _has_exact_product_link(links: _Links) -> bool:
    for href in links.hrefs:
        parsed = urlsplit(href)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "www.yin-net.com"
            and parsed.path == "/index.php"
            and parse_qs(parsed.query).get("rp") == [PRODUCT_ROUTE]
        ):
            return True
    return False


def _product_section(text: str) -> str | None:
    plans = list(_PLAN_RE.finditer(text))
    target = [match for match in plans if match.group(1) == "①"]
    if len(target) != 1:
        return None

    start = target[0].end()
    next_plan = next((match for match in plans if match.start() > target[0].start()), None)
    end = next_plan.start() if next_plan else len(text)
    section = text[start:end]
    return section or None


def _parse_price(section: str) -> float | None:
    matches = [float(value) for value in _PRICE_RE.findall(section)]
    if not matches:
        return None
    distinct = set(matches)
    if len(distinct) != 1:
        return None
    price = distinct.pop()
    return price if price >= 0 else None


def _parse_stock(section: str) -> tuple[bool | None, int | None]:
    quantities = [int(value) for value in _QUANTITY_RE.findall(section)]
    remaining = section.lower()
    out_signals = any(marker in remaining for marker in _OUT_OF_STOCK)
    for marker in _OUT_OF_STOCK:
        remaining = remaining.replace(marker, " ")
    in_signals = any(marker in remaining for marker in _IN_STOCK)

    if len(set(quantities)) > 1:
        return None, None

    quantity = quantities[0] if quantities else None
    if quantity is not None:
        if out_signals and quantity > 0:
            return None, None
        if in_signals and quantity == 0:
            return None, None
        return quantity > 0, quantity

    if out_signals and in_signals:
        return None, None
    if out_signals:
        return False, None
    if in_signals:
        return True, None
    return None, None


def parse_listing(html: str) -> dict[str, Any]:
    """Parse the official list response; ambiguous or blocked pages stay unknown."""
    result = _unknown()

    text_parser = _VisibleText()
    link_parser = _Links()
    try:
        text_parser.feed(html)
        link_parser.feed(html)
    except Exception:
        return result

    text = text_parser.text()
    lower_text = text.lower()
    if any(marker in lower_text for marker in _CHALLENGE_MARKERS):
        return result
    if len(text) < 100 or "yinnet" not in text.lower():
        return result
    if not _has_exact_product_link(link_parser):
        return result

    section = _product_section(text)
    if section is None:
        return result

    result["price"] = _parse_price(section)
    result["available"], result["quantity"] = _parse_stock(section)
    return result


def collect(timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, dict]:
    """Return the latest public stock observation for the exact Singapore VPS ①."""
    try:
        html = _fetch_html(timeout)
        result = parse_listing(html)
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, ValueError):
        result = _unknown()
    except Exception:
        # An unexpected response or parser failure must never become a stock claim.
        result = _unknown()
    return {SOURCE_KEY: result}


if __name__ == "__main__":
    print(json.dumps(collect(), ensure_ascii=False))
