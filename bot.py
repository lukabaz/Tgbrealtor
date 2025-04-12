import os
import requests
from bs4 import BeautifulSoup
import threading
import asyncio
import logging
import time
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Список пользователей, которые подписались на уведомления
subscribed_users = set()

# Хранилище ID объявлений, чтобы не дублировать
seen_ids = set()

# Хранилище фильтров для каждого пользователя
user_filters = {}

# Асинхронная функция для отправки сообщений в Telegram
async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)

# Создание клавиатуры с кнопками
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Архив", callback_data="archive"),
            InlineKeyboardButton("Графики", callback_data="charts"),
            InlineKeyboardButton("Фильтры", callback_data="filters")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    subscribed_users.add(chat_id)
    logger.info(f"User {chat_id} subscribed")
    await update.message.reply_text(
        "Вы подписались на уведомления о новых объявлениях от собственников на myhome.ge. "
        "Я буду отправлять информацию о новых объявлениях.",
        reply_markup=get_main_keyboard()
    )

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    callback_data = query.data

    if callback_data == "filters":
        # Прямой переход в Web App
        filters_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Фильтры", web_app={"url": "https://realestatege.netlify.app/filters.html"})]
        ])
        await query.message.reply_text(
            "Настройте фильтры для поиска объявлений.",
            reply_markup=filters_keyboard
        )
    elif callback_data == "archive":
        await query.message.reply_text("Архив пока не реализован.")
    elif callback_data == "charts":
        await query.message.reply_text("Графики пока не реализованы.")

# Функция парсинга объявлений с учетом фильтров
def parse_myhome(bot, loop):
    for chat_id in subscribed_users:
        filters = user_filters.get(chat_id, {})
        price_from = filters.get("price_from", 100)
        price_to = filters.get("price_to", 2000)
        floor_from = filters.get("floor_from", 1)
        floor_to = filters.get("floor_to", 30)
        rooms_from = filters.get("rooms_from", 1)
        rooms_to = filters.get("rooms_to", 5)
        bedrooms_from = filters.get("bedrooms_from", 1)
        bedrooms_to = filters.get("bedrooms_to", 2)

        # Формируем URL с фильтрами
        url = (
            f"https://www.myhome.ge/ru/s?Keyword=&Owner=1&PrTypeID=&CityID=&Furnished=&KeywordType=False&Sort=4"
            f"&PriceFrom={price_from}&PriceTo={price_to}"
            f"&FloorFrom={floor_from}&FloorTo={floor_to}"
            f"&RoomNumFrom={rooms_from}&RoomNumTo={rooms_to}"
            f"&BedroomNumFrom={bedrooms_from}&BedroomNumTo={bedrooms_to}"
        )
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        try:
            response = requests.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Failed to fetch page for chat {chat_id}: {response.status_code}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            listings = soup.find_all('div', class_='statement-card')

            for listing in listings:
                try:
                    # ID объявления
                    link_tag = listing.find('a', class_='card-container-link')
                    if not link_tag:
                        continue
                    link = "https://www.myhome.ge" + link_tag['href']
                    listing_id = link.split('/')[-1]

                    if listing_id in seen_ids:
                        continue

                    # Заголовок
                    title_tag = listing.find('div', class_='card-title')
                    title = title_tag.text.strip() if title_tag else "Без заголовка"

                    # Цена
                    price_tag = listing.find('div', class_='card-price')
                    price = price_tag.text.strip() if price_tag else "Цена не указана"

                    # Местоположение
                    location_tag = listing.find('div', class_='card-address')
                    location = location_tag.text.strip() if location_tag else "Местоположение не указано"

                    # Телефон (заглушка)
                    phone = "Телефон скрыт (нужен Selenium)"

                    # Формируем сообщение
                    message = (
                        f"Новое объявление:\n"
                        f"Заголовок: {title}\n"
                        f"Цена: {price}\n"
                        f"Местоположение: {location}\n"
                        f"Телефон: {phone}\n"
                        f"Ссылка: {link}"
                    )
                    logger.info(f"Найдено объявление для chat {chat_id}: {title}")

                    # Отправляем пользователю
                    future = asyncio.run_coroutine_threadsafe(
                        send_message(bot, chat_id, message, get_main_keyboard()),
                        loop
                    )
                    try:
                        future.result(timeout=5)
                        logger.debug(f"Message sent to {chat_id}")
                    except Exception as e:
                        logger.error(f"Failed to send message to {chat_id}: {e}")

                    seen_ids.add(listing_id)

                except Exception as e:
                    logger.error(f"Ошибка парсинга объявления для chat {chat_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка при запросе страницы для chat {chat_id}: {e}")

# Функция периодического парсинга
def run_parser(bot, loop):
    while True:
        logger.info("Проверка новых объявлений на myhome.ge...")
        parse_myhome(bot, loop)
        time.sleep(300)  # Проверка каждые 5 минут

# Обработчик данных от Web App
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug(f"Получено обновление от Web App: {update.to_dict()}")
    chat_id = update.message.chat_id
    logger.debug(f"Получены данные от Web App для chat {chat_id}")
    data = update.message.web_app_data.data
    logger.debug(f"Сырые данные Web App: {data}")
    try:
        filters_data = json.loads(data)
        user_filters[chat_id] = filters_data
        logger.info(f"Обновлены фильтры для chat {chat_id}: {filters_data}")
        await update.message.reply_text("Фильтры обновлены!", reply_markup=get_main_keyboard())
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON для chat {chat_id}: {e}, данные: {data}")
        await update.message.reply_text("Ошибка: некорректный формат данных фильтров.", reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Ошибка обработки данных Web App для chat {chat_id}: {e}")
        await update.message.reply_text("Ошибка при обновлении фильтров.", reply_markup=get_main_keyboard())

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Получаем цикл событий
    loop = asyncio.get_event_loop()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    # Настройка вебхука для Render
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    logger.info(f"Starting webhook on {webhook_url}")
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=webhook_url,
        allowed_updates=["message", "callback_query", "web_app_data"]  # Разрешаем обновления от Web App
    )

if __name__ == "__main__":
    main()