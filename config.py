import os
# from dotenv import load_dotenv
# load_dotenv()
SUPPORT_CHAT_ID = -1002578639096
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
WEBHOOK_URL = f"https://{os.getenv('VERCEL_URL', 'localhost:3000')}/{TELEGRAM_TOKEN}"  # Vercel auto VERCEL_URL, fallback for local
PORT = int(os.getenv("PORT", 3000))  # Vercel PORT auto


if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found")
if not REDIS_URL:
    raise ValueError("REDIS_URL not found")




