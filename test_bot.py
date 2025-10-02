# test_bot.py - Простая версия для тестирования
import signal
import sys
import os
import logging
from telegram.ext import Application
from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Простое логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/test_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("test_bot")

def signal_handler(signum, frame):
    """Graceful shutdown handler"""
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    sys.exit(0)

def main():
    try:
        # Настройка обработчиков сигналов для graceful shutdown
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("🚀 Starting test Telegram webhook server")
        logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
        logger.info(f"🔌 Port: {PORT}")
        
        # Проверяем переменные окружения
        logger.info(f"TELEGRAM_TOKEN: {'SET' if TELEGRAM_TOKEN else 'NOT SET'}")
        logger.info(f"PORT: {PORT}")
        
        # Инициализация Telegram бота
        bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Запускаем вебхук для Telegram
        bot_app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_TOKEN,
            webhook_url=WEBHOOK_URL,
            allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
        )
        
    except Exception as e:
        logger.error(f"❌ Error starting test bot: {e}")
        raise

if __name__ == "__main__":
    main()
