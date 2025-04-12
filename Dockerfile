FROM python:3.11-slim@sha256:17ec9dc2367aa748559d0212f34665ec4df801129de32db705ea34654b5bc77a

# Устанавливаем зависимости для Google Chrome
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем проект
COPY . .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Команда запуска приложения
CMD ["python", "bot.py"]