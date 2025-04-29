import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"
PORT = int(os.getenv("PORT", 5000))


if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found")
if not REDIS_URL:
    raise ValueError("REDIS_URL not found")




