import time
from typing import Optional, Tuple, List

from .db import DB, Product
from .parsers import fetch_price
from .notifier import send_telegram


def _fmt_price(p: Optional[float]) -> str:
    return "—" if p is None else f"${p:,.2f}"


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
        price = fetch_price(p.url, user_agent)
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