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
    fetch_timeout_seconds: int
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

    def env_int(name: str, default: int, minimum: int = 0) -> int:
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            value = default
        else:
            value = int(raw)
        return max(minimum, value)

    return Settings(
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        check_interval_minutes=env_int("CHECK_INTERVAL_MINUTES", 30, minimum=1),
        db_path=os.environ.get("DB_PATH", "./prices.db"),
        user_agent=os.environ.get("USER_AGENT", "Mozilla/5.0"),
        fetch_timeout_seconds=env_int("FETCH_TIMEOUT_SECONDS", 90, minimum=10),
        send_startup_message=env_bool("SEND_STARTUP_MESSAGE", False),
        stop_on_empty_products=env_bool("STOP_ON_EMPTY_PRODUCTS", False),
        service_alert_cooldown_minutes=env_int("SERVICE_ALERT_COOLDOWN_MINUTES", 120, minimum=0),
    )
