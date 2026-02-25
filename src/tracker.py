import logging
import time
from typing import Optional, Tuple, List
from urllib.parse import urlparse

from .db import DB, Product
from .parsers import fetch_price
from .notifier import send_telegram


def _fmt_price(p: Optional[float]) -> str:
    return "—" if p is None else f"${p:,.2f}"


def _is_valid_product_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _build_change_msg(product: Product, old: Optional[float], new: float) -> str:
    return (
        f"🔔 Цена изменилась\n\n"
        f"{product.name}\n"
        f"Было: {_fmt_price(old)}\n"
        f"Стало: {_fmt_price(new)}\n\n"
        f"{product.url}"
    )


def check_once(
    db: DB,
    token: str,
    chat_id: str,
    user_agent: str,
    notify_on_first_seen: bool = False,
) -> List[Tuple[Product, Optional[float], Optional[float]]]:
    """
    Делает один проход по товарам.
    Возвращает список (product, old_price, new_price_or_none_if_failed).
    notify_on_first_seen:
      - False: при old=None просто сохраняем last_price без уведомлений
      - True: присылаем уведомление о "первом наблюдении" (обычно не нужно,
              потому что мы будем слать общий стартовый статус)
    """
    results: List[Tuple[Product, Optional[float], Optional[float]]] = []
    products = db.list_active_products()

    for p in products:
        if not _is_valid_product_url(p.url):
            logging.warning("Skipping product '%s' due to invalid URL: %s", p.name, p.url)
            results.append((p, p.last_price, None))
            time.sleep(1)
            continue

        try:
            price = fetch_price(p.url, user_agent)
        except Exception:
            logging.exception("Failed to fetch price for product '%s' (%s)", p.name, p.url)
            results.append((p, p.last_price, None))
            time.sleep(1)
            continue

        results.append((p, p.last_price, price))

        if price is None:
            time.sleep(1)
            continue

        old = p.last_price
        db.insert_price_history(p.id, price)

        if old is None:
            # first successful fetch
            if notify_on_first_seen:
                send_telegram(
                    token,
                    chat_id,
                    f"📌 Первый замер цены\n\n{p.name}\nТекущая: {_fmt_price(price)}\n\n{p.url}",
                )
            db.update_last_price(p.id, price)
            time.sleep(2)
            continue

        if price != old:
            send_telegram(token, chat_id, _build_change_msg(p, old, price))
            db.insert_notification(p.id, old, price, "changed")
            db.update_last_price(p.id, price)

        time.sleep(2)

    return results
