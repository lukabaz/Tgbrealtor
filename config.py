import os
from dotenv import load_dotenv

# Загружаем .env для локального тестирования
load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в переменных среды или .env")

# Redis
REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise ValueError("REDIS_URL не найден в переменных среды или .env")

# Webhook URL
# На Render используем RENDER_EXTERNAL_HOSTNAME, локально — из .env
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOSTNAME:
    WEBHOOK_URL = f"https://{RENDER_HOSTNAME}/{TELEGRAM_TOKEN}"
else:
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    if not WEBHOOK_URL:
        raise ValueError("WEBHOOK_URL не найден в переменных среды или .env")

# Порт для webhook (Render устанавливает автоматически)
PORT = int(os.getenv("PORT", 10000))

# Диагностическая информация
print(f"🔧 Config loaded:")
print(f"  - TELEGRAM_TOKEN: {'SET' if TELEGRAM_TOKEN else 'NOT SET'}")
print(f"  - REDIS_URL: {'SET' if REDIS_URL else 'NOT SET'}")
print(f"  - WEBHOOK_URL: {WEBHOOK_URL}")
print(f"  - PORT: {PORT}")
print(f"  - RENDER_HOSTNAME: {os.getenv('RENDER_EXTERNAL_HOSTNAME', 'NOT SET')}")

