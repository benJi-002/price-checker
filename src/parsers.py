import re
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


def _build_proxies(proxy_url: Optional[str]) -> Optional[dict[str, str]]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def _fetch_html(
    url: str,
    user_agent: str,
    proxy_url: Optional[str] = None,
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
        timeout=timeout_seconds,
        proxies=_build_proxies(proxy_url),
    )
    if r.status_code != 200:
        return None
    return r.text


def _fetch_price_bestbuy(html: str) -> Optional[float]:
    """
    BestBuy иногда рендерит часть через JS, но на sku-страницах
    цена часто присутствует в сыром HTML как "$1,799.99".
    Берём наиболее надёжные фоллбеки:
      1) meta product:price:amount
      2) известные css-блоки
      3) regex рядом с "SKU:" или "Sold by Best Buy"
      4) общий regex по $X,XXX.XX (с ограничением на разумный диапазон)
    """
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

    # regex-фоллбек: ищем $... рядом со SKU или Sold by Best Buy
    for anchor in ["SKU:", "Sold by Best Buy"]:
        idx = html.find(anchor)
        if idx != -1:
            window = html[idx: idx + 3000]  # небольшой кусок после якоря
            m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", window)
            if m:
                return float(m.group(1).replace(",", ""))

    # общий фоллбек: первая похожая цена в документе (осторожно)
    m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if m:
        p = float(m.group(1).replace(",", ""))
        # отсекаем мусор (настрой под себя при желании)
        if 50 <= p <= 20000:
            return p

    return None


def fetch_price(
    url: str,
    user_agent: str,
    proxy_url: Optional[str] = None,
    timeout_seconds: int = 90,
) -> Optional[float]:
    host = urlparse(url).netloc.lower()
    html = _fetch_html(
        url,
        user_agent,
        proxy_url=proxy_url,
        timeout_seconds=timeout_seconds,
    )
    if html is None:
        return None

    if "bestbuy.com" in host:
        return _fetch_price_bestbuy(html)

    # Generic parsing for other sites
    soup = BeautifulSoup(html, "html.parser")

    meta = soup.select_one('meta[property="product:price:amount"]')
    if meta and meta.get("content"):
        p = _normalize_price(meta["content"])
        if p is not None:
            return p

    # basic generic fallback
    m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if m:
        return float(m.group(1).replace(",", ""))

    return None
