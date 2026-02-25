import re
import subprocess
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def _normalize_price(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.strip().replace(",", "")
    s = re.sub(r"[^0-9.]", "", s)
    if not s:
        return None
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

    soup = BeautifulSoup(html, "html.parser")

    meta = soup.select_one('meta[property="product:price:amount"]')
    if meta and meta.get("content"):
        p = _normalize_price(meta["content"])
        if p is not None:
            return p

    m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if m:
        return float(m.group(1).replace(",", ""))

    return None