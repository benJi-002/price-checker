import argparse
import logging
import time
from apscheduler.schedulers.background import BackgroundScheduler

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

    # run immediately once
    check_once(db, settings.telegram_bot_token, settings.telegram_chat_id, settings.user_agent)

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