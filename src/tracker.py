import time
from typing import Optional
from .db import DB, Product
from .parsers import fetch_price
from .notifier import send_telegram


def _fmt_price(p: Optional[float]) -> str:
    return "—" if p is None else f"${p:,.2f}"


def _should_notify(product: Product, old: Optional[float], new: float) -> Optional[str]:
    if old is None:
        return None
    if product.notify_below_price is not None and new <= product.notify_below_price:
        return "below_threshold"
    if product.notify_on_any_change and new != old:
        return "changed"
    return None


def _build_msg(product: Product, old: Optional[float], new: float, reason: str) -> str:
    header = "📉 Цена ниже порога!" if reason == "below_threshold" else "🔔 Цена изменилась"
    return (
        f"{header}\n\n"
        f"{product.name}\n"
        f"Было: {_fmt_price(old)}\n"
        f"Стало: {_fmt_price(new)}\n\n"
        f"{product.url}"
    )


def check_once(db: DB, token: str, chat_id: str, user_agent: str) -> None:
    products = db.list_active_products()

    for p in products:
        price = fetch_price(p.url, user_agent)
        if price is None:
            continue

        old = p.last_price
        db.insert_price_history(p.id, price)

        reason = _should_notify(p, old, price)
        if reason:
            send_telegram(token, chat_id, _build_msg(p, old, price, reason))
            db.insert_notification(p.id, old, price, reason)

        db.update_last_price(p.id, price)
        time.sleep(2)  # polite delay