import os
from dotenv import load_dotenv

# Загружаем .env для локального тестирования
load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    print("❌ TELEGRAM_TOKEN не найден в переменных среды")
    TELEGRAM_TOKEN = None

# Webhook URL
# На Render используем RENDER_EXTERNAL_HOSTNAME, локально — из .env
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOSTNAME:
    WEBHOOK_URL = f"https://{RENDER_HOSTNAME}/{TELEGRAM_TOKEN}" if TELEGRAM_TOKEN else None
    print(f"✅ Using RENDER_EXTERNAL_HOSTNAME: {RENDER_HOSTNAME}")
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    print(f"⚠️ RENDER_EXTERNAL_HOSTNAME not found, using WEBHOOK_URL: {WEBHOOK_URL}")

# Порт
PORT = int(os.getenv("PORT", 5000))

print(f"🔧 Config loaded:")
print(f"  - TELEGRAM_TOKEN: {'SET' if TELEGRAM_TOKEN else 'NOT SET'}")
print(f"  - WEBHOOK_URL: {WEBHOOK_URL}")
print(f"  - PORT: {PORT}")
print(f"  - RENDER_HOSTNAME: {RENDER_HOSTNAME}")
