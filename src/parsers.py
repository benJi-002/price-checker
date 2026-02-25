import json
import logging
import re
import subprocess
from typing import Optional
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup


def _normalize_price(raw: str) -> Optional[float]:
    if not raw:
        return None

    s = raw.strip().replace("\u00a0", "").replace(" ", "")
    s = re.sub(r"[^0-9.,]", "", s)
    if not s:
        return None

    # Handle mixed thousand and decimal separators:
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


def _normalize_minor_units(raw: str) -> Optional[float]:
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return None

    value = int(digits)
    if value <= 0:
        return None

    # Ozon JSON can expose minor units (e.g. 12491 -> 124.91).
    if value >= 1000:
        return value / 100.0
    return float(value)


def _fetch_html_requests(url: str, user_agent: str, timeout_seconds: int = 90) -> Optional[str]:
    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=(15, timeout_seconds),
            allow_redirects=True,
        )
    except requests.RequestException:
        logging.exception("requests fetch failed for %s", url)
        return None

    if response.status_code != 200:
        logging.warning("Fetch failed for %s: status=%s", url, response.status_code)
        return None

    return response.text


def _fetch_html_curl(
    url: str,
    user_agent: str,
    timeout_seconds: int = 90,
    force_http11: bool = True,
) -> Optional[str]:
    cmd = [
        "curl",
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
        "Accept-Language: ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "-H",
        "Cache-Control: no-cache",
        "-H",
        "Pragma: no-cache",
        url,
    ]
    if force_http11:
        cmd.insert(1, "--http1.1")

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        logging.exception("curl fetch crashed for %s", url)
        return None

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        logging.warning("curl fetch failed for %s: %s", url, stderr[:300])
        return None

    return proc.stdout


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
    for selector in selectors:
        el = soup.select_one(selector)
        if el:
            p = _normalize_price(el.get_text(" ", strip=True))
            if p is not None:
                return p

    for anchor in ["SKU:", "Sold by Best Buy"]:
        idx = html.find(anchor)
        if idx != -1:
            window = html[idx : idx + 3000]
            match = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", window)
            if match:
                return float(match.group(1).replace(",", ""))

    match = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if match:
        price = float(match.group(1).replace(",", ""))
        if 50 <= price <= 20000:
            return price

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


def _extract_ozon_price_from_text(text: str) -> Optional[float]:
    decimal_patterns = (
        r"([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{2}))\s*(?:BYN|Br|RUB)\b",
        r"(?:BYN|Br|RUB)\s*([0-9]{1,3}(?:[ \u00a0][0-9]{3})*(?:[.,][0-9]{2}))\b",
        r'"price"\s*:\s*"([0-9]+(?:[.,][0-9]{1,2})?)"',
        r'"price"\s*:\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    )
    for pattern in decimal_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        p = _normalize_price(match.group(1))
        if p is not None and 0 < p < 1_000_000:
            return p

    minor_patterns = (
        r'"(?:price|finalPrice|cardPrice|salePrice)"\s*:\s*"([0-9]{4,9})"',
        r'"(?:price|finalPrice|cardPrice|salePrice)"\s*:\s*([0-9]{4,9})',
    )
    for pattern in minor_patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            p = _normalize_minor_units(match.group(1))
            if p is not None and 1 <= p <= 1_000_000:
                return p

    return None


def _fetch_price_ozon_api(url: str, user_agent: str, timeout_seconds: int = 90) -> Optional[float]:
    parsed = urlparse(url)
    page_url = parsed.path or "/"
    if parsed.query:
        page_url = f"{page_url}?{parsed.query}"

    encoded_page_url = quote(page_url, safe="")
    api_urls = [
        # Ozon often requires __rr=1 for anti-bot redirect handshake.
        f"https://www.ozon.by/api/composer-api.bx/page/json/v2?url={encoded_page_url}&__rr=1",
        f"https://www.ozon.by/api/composer-api.bx/page/json/v2?url={encoded_page_url}",
    ]
    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.ozon.by/",
    }

    session = requests.Session()
    for api_url in api_urls:
        try:
            response = session.get(
                api_url,
                headers=headers,
                timeout=(15, timeout_seconds),
                allow_redirects=True,
            )
        except requests.RequestException:
            logging.exception("Ozon API fetch failed for %s", url)
            continue

        if response.status_code != 200:
            logging.warning("Ozon API returned status=%s for %s", response.status_code, url)
            continue

        price = _extract_ozon_price_from_text(response.text)
        if price is not None:
            return price

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

    return _extract_ozon_price_from_text(html)


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

    match = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*\.[0-9]{2})", html)
    if match:
        return float(match.group(1).replace(",", ""))

    return None


def fetch_price(url: str, user_agent: str, timeout_seconds: int = 90) -> Optional[float]:
    host = urlparse(url).netloc.lower()

    if "bestbuy.com" in host:
        html = _fetch_html_curl(url, user_agent, timeout_seconds=timeout_seconds, force_http11=True)
    elif "ozon." in host:
        # Ozon + Termux VPN: curl may get redirect loops. Prefer requests + API fallback.
        html = _fetch_html_requests(url, user_agent, timeout_seconds=timeout_seconds)
    else:
        html = _fetch_html_requests(url, user_agent, timeout_seconds=timeout_seconds)

    if "bestbuy.com" in host:
        if html is None:
            return None
        return _fetch_price_bestbuy(html)
    if "ozon." in host:
        if html is not None:
            price = _fetch_price_ozon(html)
            if price is not None:
                return price
        return _fetch_price_ozon_api(url, user_agent, timeout_seconds=timeout_seconds)

    if html is None:
        return None

    return _fetch_price_generic(html)
