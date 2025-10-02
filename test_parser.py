# test_parser.py - Простая версия для тестирования
import signal
import sys
import os
import logging
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Простое логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/test_parser.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("test_parser")

class TestParser:
    def __init__(self):
        self.scheduler = None
        self.running = False
        
    def run_parser(self):
        """Простая функция парсинга для тестирования"""
        logger.info("🚀 Test parser triggered")
        logger.info("✅ Test parser completed")

    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down parser gracefully...")
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
                id='test_parser_job',
                max_instances=1,
                coalesce=True
            )
            
            logger.info("✅ Test scheduler configured successfully")
            logger.info(f"🔁 Jobs in scheduler: {self.scheduler.get_jobs()}")
            
            # Запуск первого парсинга сразу
            logger.info("🚀 Running initial test parse...")
            self.run_parser()
            
            # Запуск планировщика
            logger.info("🚀 Starting test scheduler...")
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"❌ Error starting test parser: {e}")
            raise

if __name__ == "__main__":
    parser = TestParser()
    parser.run()
