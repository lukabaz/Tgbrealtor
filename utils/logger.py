# utils/logger.py
import logging

# Настройка логгера
logger = logging.getLogger("real_estate_bot")
logger.setLevel(logging.INFO)

# Чтобы не дублировать хендлеры, если модуль импортируется несколько раз
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Отключаем подробный лог httpx, если используется
logging.getLogger("httpx").setLevel(logging.WARNING)