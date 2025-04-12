import os
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Хранилище фильтров для каждого пользователя
user_filters = {}

# Асинхронная функция для отправки сообщений в Telegram
async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)

# Создание клавиатуры с кнопками
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("Выбрать город", callback_data="select_city")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    logger.info(f"User {chat_id} started the bot")
    await update.message.reply_text(
        "Привет! Нажми кнопку ниже, чтобы выбрать город.",
        reply_markup=get_main_keyboard()
    )

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    callback_data = query.data

    if callback_data == "select_city":
        # Прямой переход в Web App
        city_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Выбрать город", web_app={"url": "https://realestatege.netlify.app/"})]
        ])
        await query.message.reply_text(
            "Выберите город для фильтрации.",
            reply_markup=city_keyboard
        )

# Обработчик всех обновлений для отладки
async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug(f"Получено обновление: {update.to_dict()}")

# Обработчик данных от Web App
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug(f"Получено обновление от Web App: {update.to_dict()}")
    chat_id = update.message.chat_id
    logger.debug(f"Получены данные от Web App для chat {chat_id}")
    data = update.message.web_app_data.data
    logger.debug(f"Сырые данные Web App: {data}")
    try:
        city_data = json.loads(data)
        user_filters[chat_id] = city_data
        city_id = city_data.get("city")
        city_name = { "1": "Тбилиси", "2": "Батуми", "3": "Кутаиси" }.get(city_id, "Неизвестный город")
        logger.info(f"Обновлен фильтр города для chat {chat_id}: {city_data}")
        await update.message.reply_text(f"Город обновлен: {city_name}!", reply_markup=get_main_keyboard())
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON для chat {chat_id}: {e}, данные: {data}")
        await update.message.reply_text("Ошибка: некорректный формат данных.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка обработки данных Web App для chat {chat_id}: {e}")
        await update.message.reply_text("Ошибка при обновлении города.", reply_markup=get_main_keyboard())

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Произошла ошибка: {context.error}")
    if isinstance(context.error, Conflict):
        logger.error("Конфликт: другой экземпляр бота использует getUpdates. Перезапускаю polling через 10 секунд...")
        await asyncio.sleep(10)
        context.application.run_polling(allowed_updates=["message", "callback_query"])

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    # Добавляем обработчик для всех обновлений
    application.add_handler(MessageHandler(filters.ALL, debug_update), group=1)
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)

    # Запускаем polling
    logger.info("Starting polling...")
    application.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()