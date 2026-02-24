import argparse
import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler

from .tracker import check_once, _fmt_price
from .config import load_settings
from .db import DB
from .tracker import check_once


def cmd_init_db(db: DB) -> None:
    db.init()
    print("✅ DB initialized")


def cmd_add(db: DB, name: str, url: str, threshold: float | None) -> None:
    db.add_product(name=name, url=url, threshold=threshold)
    print("✅ Added:", name)


def cmd_run(db: DB, settings) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # Стартовое сообщение: режим + интервал + текущие цены
    mode = "Уведомлять о ЛЮБОМ изменении цены"
    # Первый проход — чтобы получить актуальные цены для статуса (без уведомлений о change)
    results = check_once(
        db,
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        settings.user_agent,
        notify_on_first_seen=False,
    )

    # Собираем красивый статус
    lines = [
        "✅ Price-checker запущен",
        f"Режим: {mode}",
        f"Интервал: {settings.check_interval_minutes} мин",
        "",
        "Товары:",
    ]

    if not results:
        lines.append("— (пока нет товаров в базе)")
    else:
        for (p, old, new) in results:
            if new is None:
                lines.append(f"• {p.name}: не удалось получить цену")
            else:
                # Если old is None — значит это первый успешный замер
                prefix = "•"
                lines.append(f"{prefix} {p.name}: {_fmt_price(new)}")

    from .notifier import send_telegram
    send_telegram(settings.telegram_bot_token, settings.telegram_chat_id, "\n".join(lines))

    # Планировщик
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_once,
        "interval",
        minutes=settings.check_interval_minutes,
        args=[db, settings.telegram_bot_token, settings.telegram_chat_id, settings.user_agent],
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    logging.info("Started. Interval=%d min", settings.check_interval_minutes)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
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

    if args.cmd == "init-db":
        cmd_init_db(db)
    elif args.cmd == "add":
        cmd_add(db, args.name, args.url, args.threshold)
    elif args.cmd == "run":
        cmd_run(db, settings)


if __name__ == "__main__":
    main()