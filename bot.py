import os
import logging
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

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
    args = context.args  # Получаем параметры из deep link

    if args and args[0].startswith("city_"):
        # Извлекаем город из параметра
        city_id = args[0].split("_")[1]
        user_filters[chat_id] = {"city": city_id}
        city_name = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}.get(city_id, "Неизвестный город")
        logger.info(f"User {chat_id} set city to {city_id} via deep link")
        await update.message.reply_text(
            f"Город обновлен: {city_name}!",
            reply_markup=get_main_keyboard()
        )
    else:
        logger.info(f"User {chat_id} started the bot")
        await update.message.reply_text(
            "Привет! Нажми кнопку ниже или используй кнопку 'Выбрать город' в меню бота.",
            reply_markup=get_main_keyboard()
        )

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    callback_data = query.data

    if callback_data == "select_city":
        # Прямой переход в Web App через inline-кнопку
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

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    # Добавляем обработчик для всех обновлений
    application.add_handler(MessageHandler(filters.ALL, debug_update), group=1)

    # Настройка вебхука
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    logger.info(f"Setting webhook to {webhook_url}")
    application.run_webhook(
        listen="0.0.0.0",
        port=10000,
        url_path=TOKEN,
        webhook_url=webhook_url,
        allowed_updates=["message", "callback_query"]
    )

if __name__ == "__main__":
    main()