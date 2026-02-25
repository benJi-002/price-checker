import requests
from typing import Optional


def _build_proxies(proxy_url: Optional[str]) -> Optional[dict[str, str]]:
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}


def send_telegram(token: str, chat_id: str, text: str, proxy_url: Optional[str] = None) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        json={"chat_id": chat_id, "text": text},
        timeout=20,
        proxies=_build_proxies(proxy_url),
    )
    r.raise_for_status()
