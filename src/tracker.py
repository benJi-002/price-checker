import logging
import time
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from .db import DB, Product
from .notifier import send_telegram
from .parsers import fetch_price


def _fmt_price(price: Optional[float]) -> str:
    return "--" if price is None else f"${price:,.2f}"


def _is_valid_product_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _build_change_msg(product: Product, old: Optional[float], new: float) -> str:
    return (
        "Price changed\n\n"
        f"{product.name}\n"
        f"Old: {_fmt_price(old)}\n"
        f"New: {_fmt_price(new)}\n\n"
        f"{product.url}"
    )


def check_once(
    db: DB,
    token: str,
    chat_id: str,
    user_agent: str,
    notify_on_first_seen: bool = False,
    fetch_timeout_seconds: int = 90,
) -> List[Tuple[Product, Optional[float], Optional[float]]]:
    """
    Perform one pass over active products.
    Returns list of tuples: (product, old_price, new_price_or_none_if_failed).

    notify_on_first_seen:
      - False: when old_price is None, store current price without notification.
      - True: send a first-seen message.
    """
    results: List[Tuple[Product, Optional[float], Optional[float]]] = []
    products = db.list_active_products()

    for product in products:
        if not _is_valid_product_url(product.url):
            logging.warning("Skipping product '%s' due to invalid URL: %s", product.name, product.url)
            results.append((product, product.last_price, None))
            time.sleep(1)
            continue

        try:
            price = fetch_price(
                product.url,
                user_agent,
                timeout_seconds=fetch_timeout_seconds,
            )
        except Exception:
            logging.exception("Failed to fetch price for product '%s' (%s)", product.name, product.url)
            results.append((product, product.last_price, None))
            time.sleep(1)
            continue

        results.append((product, product.last_price, price))

        if price is None:
            time.sleep(1)
            continue

        old = product.last_price
        db.insert_price_history(product.id, price)

        if old is None:
            if notify_on_first_seen:
                send_telegram(
                    token,
                    chat_id,
                    (
                        "First price seen\n\n"
                        f"{product.name}\n"
                        f"Current: {_fmt_price(price)}\n\n"
                        f"{product.url}"
                    ),
                )
            db.update_last_price(product.id, price)
            time.sleep(2)
            continue

        if price != old:
            send_telegram(
                token,
                chat_id,
                _build_change_msg(product, old, price),
            )
            db.insert_notification(product.id, old, price, "changed")
            db.update_last_price(product.id, price)

        time.sleep(2)

    return results
