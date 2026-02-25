import json
import re
import subprocess
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def _normalize_price(raw: str) -> Optional[float]:
    if not raw:
        return None

    s = raw.strip().replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None

    # Normalize decimal/thousand separators for formats like:
    # 1,234.56 | 1.234,56 | 124,91 | 124.91
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) in (1, 2):
            s = "".join(parts[:-1]) + "." + parts[-1] if len(parts) > 1 else parts[0]
        else:
            s = "".join(parts)
    elif "." in s:
        parts = s.split(".")
        if len(parts) > 2:
            s = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts) == 2 and len(parts[-1]) not in (1, 2):
            s = "".join(parts)

    try:
        return float(s)
    except ValueError:
        return None


def _fetch_html_requests(
    url: str,
    user_agent: str,
    timeout_seconds: int = 90,
) -> Optional[str]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    r = requests.get(
        url,
        headers=headers,
        timeout=(15, timeout_seconds),  # connect, read
        allow_redirects=True,
    )
    if r.status_code != 200:
        return None
    return r.text


def _fetch_html_bestbuy_curl(
    url: str,
    user_agent: str,
    timeout_seconds: int = 90,
) -> Optional[str]:
    """
    BestBuy + VPN: curl --http1.1 стабильно работает, requests иногда получает
    RemoteDisconnected. Поэтому транспорт для BestBuy делаем через curl.
    """
    cmd = [
        "curl",
        "--http1.1",
        "-L",
        "--connect-timeout",
        "15",
        "--max-time",
        str(timeout_seconds),
        "-H",
        f"User-Agent: {user_agent}",
        "-H",
        "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H",
        "Accept-Language: en-US,en;q=0.9",
        "-H",
        "Cache-Control: no-cache",
        "-H",
        "Pragma: no-cache",
        url,
    ]

    try:
        p = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if p.returncode != 0:
            # если хочешь — можно логировать p.stderr
            return None
        return p.stdout
    except Exception:
        return None


def _fetch_price_bestbuy(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")

    meta = soup.select_one('meta[property="product:price:amount"]')
    if meta and meta.get("content"):
        p = _normalize_price(meta["content"])
        if p is not None:
            return p

    selectors = [
        ".priceView-customer-price span",
        ".priceView-hero-price span",
        "[data-testid='customer-price']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            p = _normalize_price(el.get_text(" ", strip=True))
            if p is not None:
                return p

    for anchor in ["SKU:", "Sold by Best Buy"]:
        idx = html.find(anchor)
        if idx != -1:
            window = html[idx : idx + 3000]
            m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", window)
            if m:
                return float(m.group(1).replace(",", ""))

    m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if m:
        p = float(m.group(1).replace(",", ""))
        if 50 <= p <= 20000:
            return p

    return None


def _extract_json_ld_price(soup: BeautifulSoup) -> Optional[float]:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        stack = [data]
        while stack:
            node = stack.pop()

            if isinstance(node, dict):
                for key in ("price", "lowPrice", "highPrice"):
                    if key in node:
                        p = _normalize_price(str(node[key]))
                        if p is not None and 0 < p < 1_000_000:
                            return p
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    return None


def _fetch_price_ozon(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")

    for selector in (
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
        'meta[name="price"]',
    ):
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            p = _normalize_price(meta["content"])
            if p is not None:
                return p

    p = _extract_json_ld_price(soup)
    if p is not None:
        return p

    # Common Ozon money formats in HTML: "124,91 Br", "BYN 124,91"
    patterns = (
        r"([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{2}))\s*(?:BYN|Br)\b",
        r"(?:BYN|Br)\s*([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{2}))\b",
        r'"price"\s*:\s*"([0-9]+(?:[.,][0-9]{1,2})?)"',
        r'"price"\s*:\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    )
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.IGNORECASE)
        if not m:
            continue
        p = _normalize_price(m.group(1))
        if p is not None and 0 < p < 1_000_000:
            return p

    return None


def _fetch_price_generic(html: str) -> Optional[float]:
    soup = BeautifulSoup(html, "html.parser")

    for selector in (
        'meta[property="product:price:amount"]',
        'meta[property="og:price:amount"]',
        'meta[itemprop="price"]',
        'meta[name="price"]',
    ):
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            p = _normalize_price(meta["content"])
            if p is not None:
                return p

    p = _extract_json_ld_price(soup)
    if p is not None:
        return p

    # Keep USD fallback for legacy behavior.
    m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if m:
        return float(m.group(1).replace(",", ""))

    return None


def fetch_price(
    url: str,
    user_agent: str,
    timeout_seconds: int = 90,
) -> Optional[float]:
    host = urlparse(url).netloc.lower()

    if "bestbuy.com" in host:
        html = _fetch_html_bestbuy_curl(url, user_agent, timeout_seconds=timeout_seconds)
    else:
        html = _fetch_html_requests(url, user_agent, timeout_seconds=timeout_seconds)

    if html is None:
        return None

    if "bestbuy.com" in host:
        return _fetch_price_bestbuy(html)
    if "ozon." in host:
        return _fetch_price_ozon(html)
    return _fetch_price_generic(html)
