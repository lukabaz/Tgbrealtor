# Настройка переменных окружения в Render Dashboard

## Обязательные переменные для работы

### В Render Dashboard → Service → Environment:

1. **TELEGRAM_TOKEN** (обязательно)
   ```
   Key: TELEGRAM_TOKEN
   Value: 1234567890:AAAA-ваш-токен-от-BotFather
   ```

2. **PORT** (устанавливается автоматически Render)
   ```
   Key: PORT
   Value: (автоматически, обычно 10000)
   ```

3. **RENDER_EXTERNAL_HOSTNAME** (устанавливается автоматически Render)
   ```
   Key: RENDER_EXTERNAL_HOSTNAME  
   Value: (автоматически, например: yourapp.onrender.com)
   ```

## Опциональные переменные (для полной версии)

4. **REDIS_URL** (нужен для основной версии)
   ```
   Key: REDIS_URL
   Value: redis://username:password@hostname:port
   ```
   
   **Для бесплатного плана:** Можно использовать внешний Redis:
   - Redis Cloud (бесплатный план)
   - Upstash Redis (бесплатный план)
   - Railway Redis (бесплатный план)

## Проверка настроек

### Текущая проблема:
```
==> No open ports detected, continuing to scan...
```

Это означает, что:
1. Приложение не открывает порт `$PORT`
2. Или падает до открытия порта
3. Или переменные окружения не настроены

### Решение:
1. **Проверить в Render Dashboard:**
   - Service → Environment
   - Убедиться, что `TELEGRAM_TOKEN` установлен
   - `PORT` должен быть установлен автоматически
   - `RENDER_EXTERNAL_HOSTNAME` должен быть установлен автоматически

2. **Если переменные не установлены автоматически:**
   ```
   PORT=10000
   RENDER_EXTERNAL_HOSTNAME=ваш-сервис.onrender.com
   ```

## Тестовая конфигурация

**Текущий деплой использует:**
- `simple_server.py` - простой HTTP сервер на порту `$PORT`
- Должен открыть порт и показать "Hello from Render!"

**Ожидаемый результат:**
```
INFO spawned: 'test_telegram_bot' with pid 24
INFO success: test_telegram_bot entered RUNNING state
==> Detected service running on port 10000
```

## Следующие шаги

1. **Если простой сервер работает:**
   - Переключиться обратно на `test_bot.py`
   - Проверить логи для диагностики проблем с Telegram

2. **Если простой сервер не работает:**
   - Проблема в базовой конфигурации Render
   - Проверить переменные окружения
   - Проверить настройки сервиса

## Команды для переключения

### Вернуться к тестовому боту:
```bash
# В test_supervisord.conf изменить:
command=python test_bot.py  # вместо simple_server.py
```

### Вернуться к основной версии:
```bash
# В Procfile:
web: supervisord -c /etc/supervisor/conf.d/supervisord.conf

# В Dockerfile:
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```
