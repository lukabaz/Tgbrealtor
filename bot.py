# bot.py - Telegram Bot Process
import signal
import sys
import os
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT
from authorization.subscription import welcome_new_user, handle_buttons, successful_payment, pre_checkout
from authorization.webhook import webhook_update
from authorization.support import handle_user_message
from utils.logger import setup_logger

# Настройка логгера
logger = setup_logger("telegram_bot", "logs/bot.log")

class TelegramBot:
    def __init__(self):
        self.bot_app = None
        self.running = False
        
    def setup_handlers(self):
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
        
    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False
        if self.bot_app:
            logger.info("Stopping bot application...")
            # Остановка webhook будет обработана автоматически
        sys.exit(0)
        
    def run(self):
        """Запуск бота"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            self.setup_handlers()
            self.running = True
            
            logger.info("🚀 Starting Telegram webhook server")
            logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
            logger.info(f"🔌 Port: {PORT}")
            
            # Запускаем вебхук для Telegram
            self.bot_app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TELEGRAM_TOKEN,
                webhook_url=WEBHOOK_URL,
                allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
            )
            
        except Exception as e:
            logger.error(f"❌ Error starting Telegram bot: {e}")
            raise

if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()