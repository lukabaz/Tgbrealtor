# Инструкции по деплою и апгрейду Telegram-бота с парсером

## Обзор изменений

Проект был реструктурирован для решения конфликтов между Telegram webhook и Selenium парсером:

### Основные изменения:
1. **Разделение процессов**: Бот (`bot.py`) и парсер (`parser.py`) теперь работают в отдельных процессах
2. **Multi-process архитектура**: Использование `supervisord` для управления процессами
3. **Улучшенное логирование**: Логи разделены по процессам в папке `logs/`
4. **Graceful shutdown**: Корректное завершение работы при получении сигналов от Render
5. **Устранение конфликтов портов**: Каждый процесс использует свои ресурсы

## Структура файлов

```
├── bot.py              # Telegram webhook процесс
├── parser.py           # Selenium парсер процесс  
├── app.py              # Старый файл (можно удалить после тестирования)
├── supervisord.conf    # Конфигурация multi-process
├── Dockerfile          # Обновленный для supervisord
├── Procfile           # Обновленный для нового запуска
├── requirements.txt    # Добавлен supervisor
├── start.sh           # Скрипт graceful shutdown (создается в Dockerfile)
└── logs/              # Директория для логов (создается автоматически)
    ├── bot.log
    ├── parser.log
    ├── bot_stdout.log
    ├── bot_stderr.log
    ├── parser_stdout.log
    ├── parser_stderr.log
    └── supervisord.log
```

## Деплой на Render

### 1. Подготовка к деплою

Убедитесь, что в дашборде Render настроены переменные окружения:
- `TELEGRAM_TOKEN` - токен вашего Telegram бота
- `PORT` - порт для webhook (устанавливается автоматически Render)
- `REDIS_URL` - URL для подключения к Redis
- `RENDER_EXTERNAL_HOSTNAME` - устанавливается автоматически Render

### 2. Деплой изменений

```bash
# 1. Коммит изменений
git add .
git commit -m "Refactor: Multi-process architecture with supervisord"

# 2. Пуш в репозиторий
git push origin main
```

### 3. Мониторинг деплоя

После деплоя в Render:

1. **Проверьте логи деплоя** в дашборде Render
2. **Убедитесь, что оба процесса запустились**:
   - Telegram Bot: должен показать "🚀 Starting Telegram webhook server"
   - Parser: должен показать "✅ Scheduler configured successfully"

### 4. Проверка работоспособности

1. **Telegram Bot**: Отправьте сообщение боту - должен отвечать
2. **Parser**: Проверьте логи - должен запускаться каждые 6 минут
3. **Логи**: Проверьте, что логи пишутся в отдельные файлы

## Апгрейд плана Render

### Текущие ограничения Free плана:
- Инстанс засыпает после 15 минут без трафика
- 750 часов в месяц
- Парсер может не работать во время сна

### Переход на Starter план ($7/мес):

#### 1. Апгрейд в дашборде Render:
```
Dashboard → Service → Settings → Plan → Upgrade to Starter
```

#### 2. Преимущества Starter плана:
- **Постоянная работа**: Инстанс не засыпает
- **Стабильный парсинг**: Парсер работает 24/7 каждые 6 минут  
- **Улучшенная производительность**: Больше ресурсов CPU/RAM
- **Приоритетная поддержка**: Быстрее решение проблем

#### 3. После апгрейда:
- Парсер начнет работать непрерывно
- Пользователи получат уведомления в реальном времени
- Снизится нагрузка на систему (нет постоянных пробуждений)

## Мониторинг и отладка

### Просмотр логов через Render Dashboard:
```
Dashboard → Service → Logs
```

### Типы логов:
- **Build logs**: Логи сборки Docker образа
- **Deploy logs**: Логи деплоя и запуска
- **Application logs**: Логи работы приложения

### Структура логов приложения:
```
# Supervisord
[supervisord] Starting...
[telegram_bot] 🚀 Starting Telegram webhook server
[selenium_parser] ✅ Scheduler configured successfully

# Bot логи
2024-01-01 12:00:00 - telegram_bot - INFO - Setting up handlers
2024-01-01 12:00:01 - telegram_bot - INFO - ✅ Telegram bot handlers configured

# Parser логи  
2024-01-01 12:00:00 - selenium_parser - INFO - 🚀 run_parser() triggered
2024-01-01 12:06:00 - selenium_parser - INFO - Найдено активных пользователей: 5
```

### Команды для отладки (если есть SSH доступ):
```bash
# Статус процессов
supervisorctl status

# Перезапуск процесса
supervisorctl restart telegram_bot
supervisorctl restart selenium_parser

# Просмотр логов
tail -f /app/logs/bot.log
tail -f /app/logs/parser.log
tail -f /app/logs/supervisord.log
```

## Откат изменений (если нужно)

Если возникнут проблемы, можно быстро откатиться к старой версии:

```bash
# 1. Временно вернуть старый Procfile
echo "web: python app.py" > Procfile

# 2. Коммит и пуш
git add Procfile
git commit -m "Temporary rollback to single process"
git push origin main
```

## Оптимизация для продакшена

### После стабилизации на Starter плане:

1. **Удалить старый app.py**:
```bash
git rm app.py
git commit -m "Remove old app.py after successful migration"
```

2. **Настроить мониторинг**:
   - Добавить health checks для каждого процесса
   - Настроить алерты при падении процессов
   - Мониторинг использования ресурсов

3. **Оптимизация парсера**:
   - Настроить интервал парсинга под нагрузку
   - Добавить rate limiting для API запросов
   - Оптимизировать использование памяти Selenium

## Troubleshooting

### Частые проблемы:

1. **Процесс не запускается**:
   - Проверьте логи supervisord
   - Убедитесь, что все зависимости установлены
   - Проверьте переменные окружения

2. **Парсер не работает**:
   - Проверьте логи parser.log
   - Убедитесь, что Chrome/ChromeDriver установлены
   - Проверьте подключение к Redis

3. **Бот не отвечает**:
   - Проверьте webhook URL в логах
   - Убедитесь, что PORT правильно настроен
   - Проверьте TELEGRAM_TOKEN

4. **Высокое использование ресурсов**:
   - Мониторьте количество активных пользователей
   - Оптимизируйте интервал парсинга
   - Рассмотрите увеличение плана Render

## Контакты для поддержки

При возникновении проблем:
1. Проверьте логи в Render Dashboard
2. Сравните с примерами логов выше
3. Проверьте статус всех переменных окружения
4. При необходимости создайте issue в репозитории
