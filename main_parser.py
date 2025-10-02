# main_parser.py - Основной парсер без Selenium для первого теста
import signal
import sys
import os
import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/main_parser.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("main_parser")

class MainParser:
    def __init__(self):
        self.scheduler = None
        self.running = False
        
    def run_parser(self):
        """Основная функция парсинга (упрощенная)"""
        logger.info("🚀 Main parser triggered")
        
        try:
            # Имитация работы парсера
            logger.info("📊 Checking for active users...")
            logger.info("🔍 No Selenium operations for now - just testing scheduler")
            logger.info("✅ Main parser cycle completed")
            
        except Exception as e:
            logger.error(f"❌ Error in main parser: {e}")

    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down main parser gracefully...")
        self.running = False
        if self.scheduler:
            logger.info("Shutting down scheduler...")
            self.scheduler.shutdown(wait=True)
        sys.exit(0)

    def run(self):
        """Запуск парсера с планировщиком"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            self.running = True
            
            # Создаем планировщик
            self.scheduler = BlockingScheduler()
            self.scheduler.add_job(
                self.run_parser, 
                IntervalTrigger(minutes=6),
                id='main_parser_job',
                max_instances=1,
                coalesce=True
            )
            
            logger.info("✅ Main scheduler configured successfully")
            logger.info(f"🔁 Jobs in scheduler: {self.scheduler.get_jobs()}")
            
            # Запуск первого парсинга сразу
            logger.info("🚀 Running initial main parse...")
            self.run_parser()
            
            # Запуск планировщика
            logger.info("🚀 Starting main scheduler...")
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"❌ Error starting main parser: {e}")
            logger.exception("Full traceback:")
            raise

if __name__ == "__main__":
    parser = MainParser()
    parser.run()
