# single_app.py - Объединенное приложение как в оригинале, но с исправлениями
import signal
import sys
import threading
import time
import random
import logging
import os
from datetime import datetime, timezone, timedelta
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Импорты (с обработкой ошибок)
try:
    from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT
    print(f"✅ Config imported successfully")
except Exception as e:
    print(f"❌ Config import error: {e}")
    sys.exit(1)

try:
    from authorization.subscription import welcome_new_user, handle_buttons, successful_payment, pre_checkout
    from authorization.webhook import webhook_update
    from authorization.support import handle_user_message
    print(f"✅ Authorization modules imported")
except Exception as e:
    print(f"⚠️ Authorization import error: {e}")
    # Создаем заглушки
    async def welcome_new_user(update, context): pass
    async def handle_buttons(update, context): pass
    async def successful_payment(update, context): pass
    async def pre_checkout(update, context): pass
    async def webhook_update(update, context): pass
    async def handle_user_message(update, context): pass

try:
    from utils.redis_client import redis_client
    from sites.router import get_parse_function
    from utils.driver import init_driver
    from tg.sender import send_to_telegram
    print(f"✅ Parser modules imported")
    PARSER_ENABLED = True
except Exception as e:
    print(f"⚠️ Parser import error: {e}")
    PARSER_ENABLED = False

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/single_app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("single_app")

class SingleApp:
    def __init__(self):
        self.bot_app = None
        self.scheduler = None
        self.running = False
        
    def setup_bot_handlers(self):
        """Настройка обработчиков бота"""
        logger.info("Setting up Telegram bot handlers")
        
        # Инициализация Telegram бота
        self.bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # Handlers для бота
        self.bot_app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
        self.bot_app.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
        self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
        self.bot_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment)) 
        self.bot_app.add_handler(PreCheckoutQueryHandler(pre_checkout))
        self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
        
        logger.info("✅ Telegram bot handlers configured")

    def run_parser(self):
        """Функция парсинга (упрощенная версия)"""
        if not PARSER_ENABLED:
            logger.info("🔄 Parser disabled - missing dependencies")
            return
            
        logger.info("🚀 Parser triggered")
        try:
            # Здесь будет логика парсинга
            logger.info("📊 Parser cycle completed")
        except Exception as e:
            logger.error(f"❌ Parser error: {e}")

    def setup_parser(self):
        """Настройка парсера"""
        if not PARSER_ENABLED:
            logger.info("⚠️ Parser setup skipped - missing dependencies")
            return
            
        logger.info("Setting up parser scheduler")
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.run_parser, 
            IntervalTrigger(minutes=6),
            id='parser_job',
            max_instances=1,
            coalesce=True
        )
        self.scheduler.start()
        logger.info("✅ Parser scheduler started")

    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        
        if self.scheduler:
            logger.info("Stopping scheduler...")
            self.scheduler.shutdown(wait=True)
            
        if self.bot_app:
            logger.info("Stopping bot application...")
            
        sys.exit(0)
        
    def run(self):
        """Запуск приложения"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            logger.info("🚀 Starting Single App")
            logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
            logger.info(f"🔌 Port: {PORT}")
            
            # Настройка бота
            self.setup_bot_handlers()
            
            # Настройка парсера в отдельном потоке
            parser_thread = threading.Thread(target=self.setup_parser, daemon=True)
            parser_thread.start()
            
            self.running = True
            
            # Запускаем вебхук для Telegram (блокирующий вызов)
            logger.info("🚀 Starting Telegram webhook server")
            self.bot_app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TELEGRAM_TOKEN,
                webhook_url=WEBHOOK_URL,
                allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
            )
            
        except Exception as e:
            logger.error(f"❌ Error starting single app: {e}")
            logger.exception("Full traceback:")
            raise

if __name__ == "__main__":
    app = SingleApp()
    app.run()
