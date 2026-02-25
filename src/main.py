import argparse
import logging
import time
from datetime import timezone
from typing import Optional
from urllib.parse import urlparse

from apscheduler.schedulers.background import BackgroundScheduler

from .config import Settings, load_settings
from .db import DB, Product
from .notifier import send_telegram
from .tracker import _fmt_price, check_once


def _is_valid_product_url(url: str) -> bool:
    parsed = urlparse(url.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _build_startup_message(
    settings: Settings,
    results: list[tuple[Product, Optional[float], Optional[float]]],
) -> str:
    lines = [
        "Price-checker started",
        f"Interval: {settings.check_interval_minutes} min",
        "",
        "Products:",
    ]

    for product, _old_price, current_price in results:
        if current_price is None:
            lines.append(f"- {product.name}: failed to fetch price")
        else:
            lines.append(f"- {product.name}: {_fmt_price(current_price)}")

    return "\n".join(lines)


def _has_successful_prices(results: list[tuple[Product, Optional[float], Optional[float]]]) -> bool:
    return any(current_price is not None for _product, _old_price, current_price in results)


def _send_service_alert(db: DB, settings: Settings, event_key: str, message: str) -> bool:
    cooldown_seconds = settings.service_alert_cooldown_minutes * 60

    try:
        allowed = db.should_send_service_event(event_key, cooldown_seconds)
    except Exception:
        logging.exception("Failed to evaluate service alert cooldown for '%s'", event_key)
        allowed = True

    if not allowed:
        logging.warning(
            "Suppressed duplicate service alert '%s' for %d minutes",
            event_key,
            settings.service_alert_cooldown_minutes,
        )
        return False

    try:
        send_telegram(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            message,
            proxy_url=settings.telegram_proxy_url,
        )
    except Exception:
        logging.exception("Failed to send service alert '%s'", event_key)
        return False

    try:
        db.record_service_event(event_key, message)
    except Exception:
        logging.exception("Failed to persist service alert '%s'", event_key)

    return True


def cmd_init_db(db: DB) -> None:
    db.init()
    print("OK: DB initialized")


def cmd_add(db: DB, name: str, url: str, threshold: float | None) -> None:
    clean_url = url.strip()
    if not _is_valid_product_url(clean_url):
        raise ValueError("Invalid URL. Use full http(s) product URL.")

    db.add_product(name=name, url=clean_url, threshold=threshold)
    print("OK: added", name)


def cmd_run(db: DB, settings: Settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    db.init()

    products = db.list_active_products()
    invalid_products = [p for p in products if not _is_valid_product_url(p.url)]
    valid_products_count = len(products) - len(invalid_products)

    if invalid_products:
        lines = [
            "Price-checker warning: invalid product URLs found.",
            "Fix URLs (http/https). Invalid items will be skipped.",
            "",
            "Invalid products:",
        ]
        for product in invalid_products[:10]:
            bad_url = product.url if product.url else "<empty>"
            lines.append(f"- {product.name}: {bad_url}")
        if len(invalid_products) > 10:
            lines.append(f"- ...and {len(invalid_products) - 10} more")

        _send_service_alert(
            db,
            settings,
            "service_invalid_urls_detected",
            "\n".join(lines),
        )
        logging.warning("Detected %d invalid product URLs", len(invalid_products))

    if valid_products_count == 0:
        reason = (
            "Price-checker: no valid active products in DB. "
            "Add a product with: python -m src.main add \"Item\" \"https://...\""
        )
        logging.warning(reason)
        if settings.stop_on_empty_products:
            _send_service_alert(db, settings, "service_stopped_no_valid_products", reason)
            logging.error("Stopped because STOP_ON_EMPTY_PRODUCTS=1")
            return

    startup_results: Optional[list[tuple[Product, Optional[float], Optional[float]]]] = None
    if valid_products_count > 0 and settings.send_startup_message:
        try:
            startup_results = check_once(
                db,
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                settings.user_agent,
                notify_on_first_seen=False,
                fetch_proxy_url=settings.fetch_proxy_url,
                telegram_proxy_url=settings.telegram_proxy_url,
            )
        except Exception as exc:
            logging.exception("Failed during startup check")
            reason = (
                "Price-checker stopped during startup check.\n"
                f"Type: {type(exc).__name__}\n"
                f"Details: {exc}"
            )
            _send_service_alert(db, settings, "service_stopped_startup_error", reason)
            return

    scheduler: Optional[BackgroundScheduler] = None

    try:
        scheduler = BackgroundScheduler(timezone=timezone.utc)
        scheduler.add_job(
            check_once,
            "interval",
            minutes=settings.check_interval_minutes,
            args=[db, settings.telegram_bot_token, settings.telegram_chat_id, settings.user_agent],
            kwargs={
                "notify_on_first_seen": False,
                "fetch_proxy_url": settings.fetch_proxy_url,
                "telegram_proxy_url": settings.telegram_proxy_url,
            },
            max_instances=1,
            coalesce=True,
        )
        scheduler.start()
        logging.info("Started. Interval=%d min", settings.check_interval_minutes)

        if startup_results is not None and _has_successful_prices(startup_results):
            _send_service_alert(
                db,
                settings,
                "service_started",
                _build_startup_message(settings, startup_results),
            )
        elif startup_results is not None:
            logging.warning("Skipping startup Telegram message: no prices fetched successfully")

        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logging.info("Stopping by KeyboardInterrupt")
    except Exception as exc:
        logging.exception("Fatal runtime error")
        reason = (
            "Price-checker stopped due to fatal runtime error.\n"
            f"Type: {type(exc).__name__}\n"
            f"Details: {exc}"
        )
        _send_service_alert(db, settings, "service_stopped_runtime_error", reason)
    finally:
        if scheduler is not None and getattr(scheduler, "running", False):
            scheduler.shutdown(wait=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="price-checker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")

    add = sub.add_parser("add")
    add.add_argument("name")
    add.add_argument("url")
    add.add_argument("--threshold", type=float, default=None)

    sub.add_parser("run")

    args = parser.parse_args()

    settings = load_settings("config.env")
    db = DB(settings.db_path)

    try:
        if args.cmd == "init-db":
            cmd_init_db(db)
        elif args.cmd == "add":
            cmd_add(db, args.name, args.url, args.threshold)
        elif args.cmd == "run":
            cmd_run(db, settings)
    except ValueError as exc:
        parser.exit(status=2, message=f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
