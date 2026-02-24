# price-checker

Python price tracker with Telegram notifications.
Designed to run on Android (Termux) as a background service.

## Setup (Termux)
1) pkg update && pkg upgrade -y
2) pkg install -y python git nano curl sqlite termux-services termux-api
3) pip install -r requirements.txt
4) cp config.example.env config.env and fill TELEGRAM_* vars
5) python -m src.main init-db
6) python -m src.main add "Item name" "https://..." 299.99
7) python -m src.main run