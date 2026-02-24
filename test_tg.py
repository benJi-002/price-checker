import os
import requests
from dotenv import load_dotenv

load_dotenv("config.env")

token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

r = requests.post(
    f"https://api.telegram.org/bot{token}/sendMessage",
    json={"chat_id": chat_id, "text": "✅ Price checker: Telegram работает!"},
    timeout=20,
)
print(r.status_code, r.text)
r.raise_for_status()