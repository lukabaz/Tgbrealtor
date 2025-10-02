import logging
import os

def setup_logger(name, log_file):
    """Настройка логгера с записью в файл и консоль"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Чтобы не дублировать хендлеры
    if not logger.handlers:
        # Формат логов, совместимый с bot.py и parser.py
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

        # Хендлер для записи в файл
        os.makedirs("logs", exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Хендлер для вывода в консоль (для Render)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    # Отключаем подробный лог httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)

    return logger