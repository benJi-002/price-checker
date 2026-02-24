import re
from typing import Optional
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


def fetch_price(url: str, user_agent: str) -> Optional[float]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=25)
    if r.status_code != 200:
        return None

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # Generic attempts
    meta = soup.select_one('meta[property="product:price:amount"]')
    if meta and meta.get("content"):
        p = _normalize_price(meta["content"])
        if p is not None:
            return p

    # Best-effort selectors (can be adjusted per site)
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

    # Fallback: JSON snippets
    m = re.search(r'"currentPrice"\s*:\s*{[^}]*"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)', html)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None

    return None