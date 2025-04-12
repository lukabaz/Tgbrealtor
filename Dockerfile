# Используем Python 3.11.12 на основе Debian 12 (Bookworm)
FROM python:3.11.12-slim-bookworm

# Устанавливаем минимальные зависимости
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем проект
COPY . .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Открываем порт для вебхука
EXPOSE 10000

# Команда запуска приложения
CMD ["python", "bot.py"]