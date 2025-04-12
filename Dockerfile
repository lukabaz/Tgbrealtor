# Используем Python 3.11.12 на основе Debian 12 (Bookworm)
FROM python:3.11.12-slim-bookworm

# Устанавливаем зависимости для Google Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libnspr4 \
    libnss3 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libxkbcommon0 \
    libxshmfence1 \
    libglu1-mesa \
    libgconf-2-4 \
    libfontconfig1 \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Chrome for Testing (CfT) для стабильной версии
ENV CHROME_VERSION=126.0.6478.126
RUN wget -q --no-check-certificate -O /tmp/chrome-linux64.zip \
    "https://storage.googleapis.com/chrome-for-testing-public/${CHROME_VERSION}/linux64/chrome-linux64.zip" \
    && unzip /tmp/chrome-linux64.zip -d /opt \
    && ln -s /opt/chrome-linux64/chrome /usr/bin/google-chrome \
    && rm /tmp/chrome-linux64.zip

# Проверяем, что Chrome установлен
RUN which google-chrome || echo "Google Chrome binary not found!" \
    && google-chrome --version || echo "Failed to get Chrome version!"

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем проект
COPY . .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открываем порт для вебхука (Render использует 10000 по умолчанию)
EXPOSE 10000

# Команда запуска приложения
CMD ["python", "bot.py"]