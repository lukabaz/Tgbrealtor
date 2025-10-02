# Инструкции по отладке проблем деплоя

## Проблема
Оба процесса (telegram_bot и selenium_parser) падают с `exit status 1` из-за ошибок импортов и зависимостей.

## Решение: Поэтапная отладка

### Шаг 1: Тестовая конфигурация (ТЕКУЩАЯ)

Создана упрощенная версия для проверки базовой функциональности:

**Файлы для тестирования:**
- `test_bot.py` - упрощенный бот без сложных импортов
- `test_parser.py` - упрощенный парсер без Selenium
- `test_supervisord.conf` - конфигурация для тестовых файлов

**Текущая конфигурация Render:**
```
Procfile: web: supervisord -c /etc/supervisor/conf.d/test_supervisord.conf
Dockerfile: CMD ["supervisord", "-c", "/etc/supervisor/conf.d/test_supervisord.conf"]
```

### Шаг 2: Проверка тестовой версии

После деплоя проверьте логи:

**Ожидаемые логи (успех):**
```
INFO supervisord started with pid 1
INFO spawned: 'test_telegram_bot' with pid 26
INFO spawned: 'test_selenium_parser' with pid 27
INFO success: test_telegram_bot entered RUNNING state
INFO success: test_selenium_parser entered RUNNING state
```

**Если тестовая версия работает:**
- Переходим к Шагу 3 (исправление основных файлов)

**Если тестовая версия не работает:**
- Проблема в базовой конфигурации Render/Docker

### Шаг 3: Исправление основных файлов

#### Проблемы в коде:

1. **utils/telegram_utils.py** - исправлен импорт logger
2. **supervisord.conf** - убраны конфликтующие stderr_logfile
3. **Импорты в authorization/** - нужно проверить все зависимости

#### Команды для возврата к основной версии:

```bash
# 1. Вернуть основную конфигурацию
# Procfile
echo "web: supervisord -c /etc/supervisor/conf.d/supervisord.conf" > Procfile

# 2. Dockerfile - изменить CMD
# CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

# 3. Коммит и деплой
git add .
git commit -m "Fix: Return to main configuration after testing"
git push origin main
```

### Шаг 4: Диагностика ошибок

#### Проверка зависимостей:
```python
# Добавить в начало bot.py для диагностики
try:
    from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT
    print(f"✅ Config imported: TOKEN={'SET' if TELEGRAM_TOKEN else 'NOT SET'}")
except Exception as e:
    print(f"❌ Config import error: {e}")

try:
    from utils.logger import setup_logger
    print("✅ Logger imported successfully")
except Exception as e:
    print(f"❌ Logger import error: {e}")

try:
    from authorization.subscription import welcome_new_user
    print("✅ Authorization imported successfully")  
except Exception as e:
    print(f"❌ Authorization import error: {e}")
```

#### Проверка переменных окружения:
```python
import os
print(f"TELEGRAM_TOKEN: {'SET' if os.getenv('TELEGRAM_TOKEN') else 'NOT SET'}")
print(f"PORT: {os.getenv('PORT', 'NOT SET')}")
print(f"REDIS_URL: {'SET' if os.getenv('REDIS_URL') else 'NOT SET'}")
print(f"RENDER_EXTERNAL_HOSTNAME: {os.getenv('RENDER_EXTERNAL_HOSTNAME', 'NOT SET')}")
```

### Шаг 5: Пошаговое восстановление

#### 5.1 Сначала только бот:
```python
# Временно отключить parser в supervisord.conf
[program:selenium_parser]
autostart=false  # Изменить на false
```

#### 5.2 Потом добавить парсер:
```python
# После успешного запуска бота включить парсер
[program:selenium_parser]
autostart=true  # Вернуть на true
```

### Шаг 6: Альтернативное решение

Если проблемы продолжаются, можно использовать более простую архитектуру:

#### Вариант A: Один процесс с threading
```python
# single_app.py
import threading
from telegram.ext import Application
from apscheduler.schedulers.background import BackgroundScheduler

def run_bot():
    # Код бота
    pass

def run_parser():
    # Код парсера  
    pass

if __name__ == "__main__":
    # Запуск парсера в отдельном потоке
    parser_thread = threading.Thread(target=run_parser, daemon=True)
    parser_thread.start()
    
    # Запуск бота в главном потоке
    run_bot()
```

#### Вариант B: Использование asyncio
```python
import asyncio
from telegram.ext import Application

async def main():
    # Запуск бота и парсера асинхронно
    bot_task = asyncio.create_task(run_bot())
    parser_task = asyncio.create_task(run_parser())
    
    await asyncio.gather(bot_task, parser_task)

if __name__ == "__main__":
    asyncio.run(main())
```

## Текущий статус

**✅ Готово:**
- Тестовые файлы созданы
- Конфигурация переключена на тестовую
- Исправлены основные ошибки импортов

**🔄 Следующие шаги:**
1. Деплой тестовой версии
2. Проверка логов
3. Поэтапное возвращение к основной версии
4. Исправление оставшихся ошибок

**📞 Для связи:**
- Проверяйте логи в Render Dashboard
- Сравнивайте с ожидаемыми результатами выше
- При необходимости откатывайтесь к рабочим версиям
