# working_app.py - Возврат к рабочей архитектуре с aiohttp
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone, timedelta

from aiohttp import web
from telegram.ext import Application
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Импорты конфигурации
from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/working_app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("working_app")

class WorkingApp:
    def __init__(self):
        self.bot_app = None
        self.web_app = None
        self.scheduler = None
        self.running = False
        
    async def webhook_handler(self, request):
        """Обработчик webhook от Telegram"""
        try:
            data = await request.json()
            logger.info(f"📨 Received webhook: {data}")
            
            # Здесь будет обработка webhook
            # Пока просто логируем
            
            return web.Response(text="OK")
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return web.Response(text="ERROR", status=500)
    
    def setup_web_app(self):
        """Настройка aiohttp веб-приложения"""
        self.web_app = web.Application()
        
        # Маршруты
        self.web_app.router.add_post(f'/{TELEGRAM_TOKEN}', self.webhook_handler)
        
        logger.info("✅ Web app routes configured")
    
    def setup_telegram_bot(self):
        """Настройка Telegram бота"""
        try:
            self.bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
            logger.info("✅ Telegram bot initialized")
        except Exception as e:
            logger.error(f"❌ Bot setup error: {e}")
    
    def run_parser(self):
        """Функция парсинга (заглушка)"""
        logger.info("🚀 Parser cycle started")
        try:
            # Здесь будет логика парсинга
            logger.info("📊 Parser cycle completed")
        except Exception as e:
            logger.error(f"❌ Parser error: {e}")

    def setup_parser(self):
        """Настройка парсера"""
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
            
        sys.exit(0)
        
    async def run_async(self):
        """Асинхронный запуск приложения"""
        try:
            logger.info("🚀 Starting Working App")
            logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
            logger.info(f"🔌 Port: {PORT}")
            
            # Настройка компонентов
            self.setup_web_app()
            self.setup_telegram_bot()
            
            # Настройка парсера в отдельном потоке
            parser_thread = threading.Thread(target=self.setup_parser, daemon=True)
            parser_thread.start()
            
            self.running = True
            
            # Запуск веб-сервера
            runner = web.AppRunner(self.web_app)
            await runner.setup()
            
            site = web.TCPSite(runner, '0.0.0.0', PORT)
            await site.start()
            
            logger.info(f"🌐 Web server started on 0.0.0.0:{PORT}")
            logger.info("✅ Application is ready!")
            
            # Держим приложение работающим
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Error in async run: {e}")
            logger.exception("Full traceback:")
            raise
    
    def run(self):
        """Запуск приложения"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            # Запуск асинхронного цикла
            asyncio.run(self.run_async())
            
        except Exception as e:
            logger.error(f"❌ Error starting working app: {e}")
            logger.exception("Full traceback:")
            raise

if __name__ == "__main__":
    app = WorkingApp()
    app.run()
