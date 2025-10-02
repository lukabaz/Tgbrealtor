# main_bot.py - Основной бот без сложных зависимостей
import signal
import sys
import os
import logging
from telegram.ext import Application, MessageHandler, filters
from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/main_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("main_bot")

class MainTelegramBot:
    def __init__(self):
        self.bot_app = None
        self.running = False
        
    async def handle_message(self, update, context):
        """Простой обработчик сообщений"""
        chat_id = update.message.chat_id
        text = update.message.text
        logger.info(f"Received message from {chat_id}: {text}")
        await context.bot.send_message(chat_id=chat_id, text="✅ Бот работает!")
        
    def setup_handlers(self):
        """Настройка обработчиков бота"""
        logger.info("Setting up main bot handlers")
        
        # Инициализация Telegram бота
        self.bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Простой обработчик сообщений
        self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        logger.info("✅ Main bot handlers configured")
        
    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        if self.bot_app:
            logger.info("Stopping bot application...")
        sys.exit(0)
        
    def run(self):
        """Запуск бота"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            self.setup_handlers()
            self.running = True
            
            logger.info("🚀 Starting main Telegram webhook server")
            logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
            logger.info(f"🔌 Port: {PORT}")
            
            # Запускаем вебхук для Telegram
            self.bot_app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TELEGRAM_TOKEN,
                webhook_url=WEBHOOK_URL,
                allowed_updates=["message"]
            )
            
        except Exception as e:
            logger.error(f"❌ Error starting main bot: {e}")
            logger.exception("Full traceback:")
            raise

if __name__ == "__main__":
    bot = MainTelegramBot()
    bot.run()
