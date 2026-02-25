import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    check_interval_minutes: int
    db_path: str
    user_agent: str
    send_startup_message: bool
    stop_on_empty_products: bool
    service_alert_cooldown_minutes: int


def load_settings(env_path: str = "config.env") -> Settings:
    load_dotenv(env_path)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in config.env")

    def env_bool(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        check_interval_minutes=int(os.environ.get("CHECK_INTERVAL_MINUTES", "30")),
        db_path=os.environ.get("DB_PATH", "./prices.db"),
        user_agent=os.environ.get("USER_AGENT", "Mozilla/5.0"),
        send_startup_message=env_bool("SEND_STARTUP_MESSAGE", False),
        stop_on_empty_products=env_bool("STOP_ON_EMPTY_PRODUCTS", False),
        service_alert_cooldown_minutes=max(
            0,
            int(os.environ.get("SERVICE_ALERT_COOLDOWN_MINUTES", "120")),
        ),
    )
