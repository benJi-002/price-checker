# price-checker

Python price tracker with Telegram notifications.
Designed to run on Android (Termux) as a background service.

## Setup (Termux)
1) pkg update && pkg upgrade -y
2) pkg install -y python git nano curl sqlite termux-services termux-api
3) pip install -r requirements.txt
4) cp config.example.env config.env and fill TELEGRAM_* vars
5) python -m src.main init-db
6) python -m src.main add "Item name" "https://..." --threshold 299.99
7) python -m src.main run

## Network
- Run tracker under system VPN (for example, Surfshark) if regional routing is needed.
- Increase `FETCH_TIMEOUT_SECONDS` for slow VPN paths (default is `90`).

## Anti-spam and stop behavior
- Startup message is disabled by default (`SEND_STARTUP_MESSAGE=0`). If enabled, it is sent only when at least one price is fetched successfully on startup.
- Invalid product URLs are blocked on `add`; existing invalid rows are skipped with warning.
- Service alerts (startup/stop/fatal) are deduplicated with cooldown via `SERVICE_ALERT_COOLDOWN_MINUTES`.
- If `STOP_ON_EMPTY_PRODUCTS=1`, service sends stop reason to Telegram and exits when no valid active products exist.
