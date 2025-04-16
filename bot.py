import os
import logging
import json
import asyncio
import redis
import re
import requests
from bs4 import BeautifulSoup
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Подключение к Redis
redis_url = os.getenv("REDIS_URL")
redis_client = redis.from_url(redis_url, decode_responses=True)

# Асинхронная функция для отправки сообщений в Telegram
async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)

# Клавиатура Web App
SETTINGS_URL = os.getenv("SETTINGS_URL", "https://realestatege.netlify.app/")
def get_settings_keyboard():
    keyboard = [[InlineKeyboardButton("Открыть настройки", web_app={"url": SETTINGS_URL})]]
    return InlineKeyboardMarkup(keyboard)

# Работа с Redis

def save_filters(chat_id: int, filters: dict):
    try:
        redis_client.set(f"filters:{chat_id}", json.dumps(filters))
    except Exception as e:
        logger.error(f"Error saving filters: {e}")

def load_filters(chat_id: int) -> dict:
    try:
        data = redis_client.get(f"filters:{chat_id}")
        return json.loads(data) if data else {}
    except Exception as e:
        logger.error(f"Error loading filters: {e}")
        return {}

def get_subscribed_users() -> set:
    try:
        data = redis_client.get("subscribed_users")
        return set(json.loads(data)) if data else set()
    except Exception as e:
        logger.error(f"Error loading subscribed users: {e}")
        return set()

def add_subscriber(chat_id: int):
    users = get_subscribed_users()
    users.add(chat_id)
    redis_client.set("subscribed_users", json.dumps(list(users)))

def remove_subscriber(chat_id: int):
    users = get_subscribed_users()
    users.discard(chat_id)
    redis_client.set("subscribed_users", json.dumps(list(users)))

def get_seen_ids() -> set:
    try:
        data = redis_client.get("seen_ids")
        return set(json.loads(data)) if data else set()
    except Exception as e:
        logger.error(f"Error loading seen_ids: {e}")
        return set()

def add_seen_id(listing_id: str):
    seen_ids = get_seen_ids()
    seen_ids.add(listing_id)
    redis_client.set("seen_ids", json.dumps(list(seen_ids)))

# Парсинг объявлений с учетом фильтров

def parse_myhome(bot, loop):
    users = get_subscribed_users()
    seen_ids = get_seen_ids()

    for chat_id in users:
        filters = load_filters(chat_id)
        city = filters.get("city", "1")
        deal_type = filters.get("deal_type", "0")
        price_from = filters.get("price_from", 100)
        price_to = filters.get("price_to", 2000)
        floor_from = filters.get("floor_from", 1)
        floor_to = filters.get("floor_to", 30)
        rooms_from = filters.get("rooms_from", 1)
        rooms_to = filters.get("rooms_to", 5)
        bedrooms_from = filters.get("bedrooms_from", 1)
        bedrooms_to = filters.get("bedrooms_to", 2)
        own_ads = filters.get("own_ads", "1")

        pr_type = {"rent": "1", "sale": "2"}.get(deal_type, "")
        url = (
            f"https://www.myhome.ge/ru/s?Keyword=&Owner={own_ads}&PrTypeID={pr_type}&CityID={city}"
            f"&Furnished=&KeywordType=False&Sort=4&PriceFrom={price_from}&PriceTo={price_to}"
            f"&FloorFrom={floor_from}&FloorTo={floor_to}&RoomNumFrom={rooms_from}&RoomNumTo={rooms_to}"
            f"&BedroomNumFrom={bedrooms_from}&BedroomNumTo={bedrooms_to}"
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.warning(f"[{chat_id}] Myhome returned {response.status_code}")
                continue
        except Exception as e:
            logger.error(f"[{chat_id}] Error fetching: {e}")
            continue

        soup = BeautifulSoup(response.text, 'html.parser')
        listings = soup.find_all('div', class_='statement-card')

        for listing in listings:
            try:
                link_tag = listing.find('a', class_='card-container-link')
                if not link_tag:
                    continue
                link = "https://www.myhome.ge" + link_tag['href']
                listing_id = link.split('/')[-1]

                if listing_id in seen_ids:
                    continue

                title = listing.find('div', class_='card-title')
                price = listing.find('div', class_='card-price')
                location = listing.find('div', class_='card-address')

                message = (
                    f"Новое объявление:\n"
                    f"Заголовок: {title.text.strip() if title else 'Без заголовка'}\n"
                    f"Цена: {price.text.strip() if price else 'Цена не указана'}\n"
                    f"Местоположение: {location.text.strip() if location else 'Местоположение не указано'}\n"
                    f"Телефон: Телефон скрыт (нужен Selenium)\n"
                    f"Ссылка: {link}"
                )

                future = asyncio.run_coroutine_threadsafe(
                    send_message(bot, chat_id, message, get_settings_keyboard()),
                    loop
                )
                future.result(timeout=5)
                add_seen_id(listing_id)

            except Exception as e:
                logger.error(f"Ошибка обработки объявления [{chat_id}]: {e}")

# Запуск парсера в потоке

def run_parser(bot, loop):
    while True:
        logger.info("Проверка новых объявлений...")
        parse_myhome(bot, loop)
        time.sleep(300)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    add_subscriber(chat_id)
    await update.message.reply_text("Добро пожаловать! Объявления будут приходить при появлении новых.\nИспользуйте /stop для отписки.", reply_markup=get_settings_keyboard())

# Команда /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    remove_subscriber(chat_id)
    await update.message.reply_text("Вы отписались от обновлений.")

# Инициализация бота

def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))

    # Запуск парсера в отдельном потоке
    loop = asyncio.get_event_loop()
    threading.Thread(target=run_parser, args=(application.bot, loop), daemon=True).start()

    application.run_polling()

if __name__ == "__main__":
    main()