FROM python:3.12-slim

WORKDIR /app
COPY . .

# Создание директории для логов
RUN mkdir -p /app/logs

# Установка системных зависимостей включая supervisor
RUN apt-get update && apt-get install -y \
    wget unzip curl gnupg supervisor \
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
    pip install --no-cache-dir -r requirements.txt && \
    pip list | grep python-telegram-bot && \
    python -c "import telegram; print('telegram module imported successfully')"

# Копирование конфигурации supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY test_supervisord.conf /etc/supervisor/conf.d/test_supervisord.conf

# Создание скрипта запуска с graceful shutdown
RUN echo '#!/bin/bash\n\
trap "echo \"Received SIGTERM, shutting down gracefully...\"; supervisorctl stop all; exit 0" SIGTERM\n\
echo "Starting supervisord..."\n\
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf' > /app/start.sh && chmod +x /app/start.sh

# Установка переменных окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose порт для webhook
EXPOSE $PORT

CMD ["supervisord", "-c", "/etc/supervisor/conf.d/test_supervisord.conf"]