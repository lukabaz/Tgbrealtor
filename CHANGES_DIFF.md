# Diff изменений для решения конфликтов Telegram Bot + Selenium Parser

## 1. Новый файл: `bot.py` (Telegram Bot Process)

```diff
+ # bot.py - Telegram Bot Process
+ import signal
+ import sys
+ import logging
+ import os
+ from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
+ from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT
+ from authorization.subscription import welcome_new_user, handle_buttons, successful_payment, pre_checkout
+ from authorization.webhook import webhook_update
+ from authorization.support import handle_user_message
+ 
+ # Создаем директорию для логов
+ os.makedirs("logs", exist_ok=True)
+ 
+ # Настройка логирования для бота
+ logging.basicConfig(
+     level=logging.INFO,
+     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
+     handlers=[
+         logging.FileHandler("logs/bot.log", encoding="utf-8"),
+         logging.StreamHandler()
+     ]
+ )
+ 
+ logger = logging.getLogger("telegram_bot")
+ 
+ class TelegramBot:
+     def __init__(self):
+         self.bot_app = None
+         self.running = False
+         
+     def setup_handlers(self):
+         """Настройка обработчиков бота"""
+         logger.info("Setting up Telegram bot handlers")
+         
+         # Инициализация Telegram бота
+         self.bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
+         
+         # Handlers для бота
+         self.bot_app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
+         self.bot_app.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
+         self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
+         self.bot_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment)) 
+         self.bot_app.add_handler(PreCheckoutQueryHandler(pre_checkout))
+         self.bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
+         
+         logger.info("✅ Telegram bot handlers configured")
+         
+     def signal_handler(self, signum, frame):
+         """Graceful shutdown handler"""
+         logger.info(f"Received signal {signum}, shutting down gracefully...")
+         self.running = False
+         if self.bot_app:
+             logger.info("Stopping bot application...")
+             # Остановка webhook будет обработана автоматически
+         sys.exit(0)
+         
+     def run(self):
+         """Запуск бота"""
+         try:
+             # Настройка обработчиков сигналов для graceful shutdown
+             signal.signal(signal.SIGTERM, self.signal_handler)
+             signal.signal(signal.SIGINT, self.signal_handler)
+             
+             self.setup_handlers()
+             self.running = True
+             
+             logger.info("🚀 Starting Telegram webhook server")
+             logger.info(f"📡 Webhook URL: {WEBHOOK_URL}")
+             logger.info(f"🔌 Port: {PORT}")
+             
+             # Запускаем вебхук для Telegram
+             self.bot_app.run_webhook(
+                 listen="0.0.0.0",
+                 port=PORT,
+                 url_path=TELEGRAM_TOKEN,
+                 webhook_url=WEBHOOK_URL,
+                 allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
+             )
+             
+         except Exception as e:
+             logger.error(f"❌ Error starting Telegram bot: {e}")
+             raise
+ 
+ if __name__ == "__main__":
+     bot = TelegramBot()
+     bot.run()
```

## 2. Новый файл: `parser.py` (Selenium Parser Process)

```diff
+ # parser.py - Selenium Parser Process
+ import signal
+ import sys
+ import time
+ import random
+ import logging
+ import os
+ from datetime import datetime, timezone, timedelta
+ from apscheduler.schedulers.blocking import BlockingScheduler
+ from apscheduler.triggers.interval import IntervalTrigger
+ from selenium.webdriver.common.by import By
+ from selenium.webdriver.support.ui import WebDriverWait
+ from selenium.webdriver.support import expected_conditions as EC
+ from selenium.common.exceptions import NoSuchElementException, TimeoutException
+ 
+ from utils.redis_client import redis_client
+ from sites.router import get_parse_function
+ from utils.driver import init_driver
+ from tg.sender import send_to_telegram
+ 
+ # Создаем директорию для логов
+ os.makedirs("logs", exist_ok=True)
+ 
+ # Настройка логирования для парсера
+ logging.basicConfig(
+     level=logging.INFO,
+     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
+     handlers=[
+         logging.FileHandler("logs/parser.log", encoding="utf-8"),
+         logging.StreamHandler()
+     ]
+ )
+ 
+ logger = logging.getLogger("selenium_parser")
+ 
+ class SeleniumParser:
+     def __init__(self):
+         self.scheduler = None
+         self.running = False
+         
+     # ... (методы парсинга перенесены из app.py с улучшениями)
+     
+     def signal_handler(self, signum, frame):
+         """Graceful shutdown handler"""
+         logger.info(f"Received signal {signum}, shutting down parser gracefully...")
+         self.running = False
+         if self.scheduler:
+             logger.info("Shutting down scheduler...")
+             self.scheduler.shutdown(wait=True)
+         sys.exit(0)
+ 
+     def run(self):
+         """Запуск парсера с планировщиком"""
+         try:
+             # Настройка обработчиков сигналов для graceful shutdown
+             signal.signal(signal.SIGTERM, self.signal_handler)
+             signal.signal(signal.SIGINT, self.signal_handler)
+             
+             self.running = True
+             
+             # Создаем планировщик
+             self.scheduler = BlockingScheduler()
+             self.scheduler.add_job(
+                 self.run_parser, 
+                 IntervalTrigger(minutes=6),
+                 id='parser_job',
+                 max_instances=1,
+                 coalesce=True
+             )
+             
+             logger.info("✅ Scheduler configured successfully")
+             logger.info(f"🔁 Jobs in scheduler: {self.scheduler.get_jobs()}")
+             
+             # Запуск первого парсинга сразу
+             logger.info("🚀 Running initial parse...")
+             self.run_parser()
+             
+             # Запуск планировщика
+             logger.info("🚀 Starting scheduler...")
+             self.scheduler.start()
+             
+         except Exception as e:
+             logger.error(f"❌ Error starting parser: {e}")
+             raise
+ 
+ if __name__ == "__main__":
+     parser = SeleniumParser()
+     parser.run()
```

## 3. Новый файл: `supervisord.conf`

```diff
+ [supervisord]
+ nodaemon=true
+ user=root
+ logfile=/app/logs/supervisord.log
+ pidfile=/app/logs/supervisord.pid
+ childlogdir=/app/logs
+ 
+ [unix_http_server]
+ file=/tmp/supervisor.sock
+ chmod=0700
+ 
+ [supervisorctl]
+ serverurl=unix:///tmp/supervisor.sock
+ 
+ [rpcinterface:supervisor]
+ supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface
+ 
+ [program:telegram_bot]
+ command=python bot.py
+ directory=/app
+ user=root
+ autostart=true
+ autorestart=true
+ redirect_stderr=true
+ stdout_logfile=/app/logs/bot_stdout.log
+ stdout_logfile_maxbytes=10MB
+ stdout_logfile_backups=3
+ stderr_logfile=/app/logs/bot_stderr.log
+ stderr_logfile_maxbytes=10MB
+ stderr_logfile_backups=3
+ environment=PATH="/usr/local/bin:/usr/bin:/bin"
+ priority=100
+ startsecs=10
+ startretries=3
+ stopwaitsecs=30
+ stopsignal=TERM
+ 
+ [program:selenium_parser]
+ command=python parser.py
+ directory=/app
+ user=root
+ autostart=true
+ autorestart=true
+ redirect_stderr=true
+ stdout_logfile=/app/logs/parser_stdout.log
+ stdout_logfile_maxbytes=10MB
+ stdout_logfile_backups=3
+ stderr_logfile=/app/logs/parser_stderr.log
+ stderr_logfile_maxbytes=10MB
+ stderr_logfile_backups=3
+ environment=PATH="/usr/local/bin:/usr/bin:/bin"
+ priority=200
+ startsecs=10
+ startretries=3
+ stopwaitsecs=30
+ stopsignal=TERM
```

## 4. Изменения в `Dockerfile`

```diff
  FROM python:3.12-slim
  
  WORKDIR /app
  COPY . .
  
+ # Создание директории для логов
+ RUN mkdir -p /app/logs
+ 
- # Установка Chrome и ChromeDriver
+ # Установка системных зависимостей включая supervisor
  RUN apt-get update && apt-get install -y \
-     wget unzip curl gnupg \
+     wget unzip curl gnupg supervisor \
      fonts-liberation libnss3 libxss1 libasound2t64 libatk-bridge2.0-0 libgtk-3-0 libdrm2 libgbm1 \
      --no-install-recommends && \
      wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor > /usr/share/keyrings/google-chrome.gpg && \
      echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
      apt-get update && \
      apt-get install -y google-chrome-stable && \
      CHROMEDRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE) && \
      wget -q -O /tmp/chromedriver.zip https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip && \
      unzip /tmp/chromedriver.zip -d /usr/local/bin/ && \
      chmod +x /usr/local/bin/chromedriver && \
      rm -rf /var/lib/apt/lists/* /tmp/* /etc/apt/sources.list.d/google-chrome.list
  
  # Установка Python-зависимостей
  RUN pip install --no-cache-dir --upgrade pip && \
      pip install --no-cache-dir python-telegram-bot[webhooks]==21.10 && \
      pip install --no-cache-dir -r requirements.txt && \
      pip list | grep python-telegram-bot && \
      python -c "import telegram; print('telegram module imported successfully')"
  
+ # Копирование конфигурации supervisord
+ COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
+ 
+ # Создание скрипта запуска с graceful shutdown
+ RUN echo '#!/bin/bash\n\
+ trap "echo \"Received SIGTERM, shutting down gracefully...\"; supervisorctl stop all; exit 0" SIGTERM\n\
+ echo "Starting supervisord..."\n\
+ exec supervisord -c /etc/supervisor/conf.d/supervisord.conf &\n\
+ wait $!' > /app/start.sh && chmod +x /app/start.sh
+ 
+ # Установка переменных окружения для supervisor
+ ENV PYTHONUNBUFFERED=1
+ ENV PYTHONPATH=/app
+ 
+ # Expose порт для webhook
+ EXPOSE $PORT
+ 
- CMD ["python", "app.py"]
+ CMD ["/app/start.sh"]
```

## 5. Изменения в `requirements.txt`

```diff
  python-telegram-bot[webhooks]==21.10
  orjson==3.10.18
  selenium==4.31.0
  redis==5.2.1
  requests==2.32.3
  flask==2.3.3
  apscheduler==3.10.4
  python-dotenv==1.0.0
+ supervisor==4.2.5
```

## 6. Изменения в `Procfile`

```diff
- worker: python bot.py
+ web: /app/start.sh
```

## Основные преимущества изменений:

### ✅ Решенные проблемы:
1. **Конфликт процессов**: Бот и парсер работают независимо
2. **Блокировка webhook**: `run_webhook()` больше не блокирует парсер
3. **Конфликт портов**: Каждый процесс использует свои ресурсы
4. **Отсутствие graceful shutdown**: Добавлена корректная обработка сигналов
5. **Плохое логирование**: Логи разделены по процессам и файлам

### 🚀 Новые возможности:
1. **Multi-process архитектура** с supervisord
2. **Автоматический перезапуск** процессов при сбоях
3. **Раздельное логирование** для каждого процесса
4. **Graceful shutdown** для корректного завершения на Render
5. **Готовность к Starter плану** для 24/7 работы парсера

### 📊 Мониторинг:
- `logs/bot.log` - логи Telegram бота
- `logs/parser.log` - логи Selenium парсера
- `logs/supervisord.log` - логи управления процессами
- `logs/*_stdout.log` - стандартный вывод процессов
- `logs/*_stderr.log` - ошибки процессов
