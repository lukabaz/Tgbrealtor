import os
import logging
import json
import asyncio
import redis
import re
from bs4 import BeautifulSoup
import threading
import time
import random
import cloudscraper
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('bot.log')]
)
logger = logging.getLogger(__name__)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('cloudscraper').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.WARNING)
logging.getLogger(__name__).setLevel(logging.DEBUG)

# Проверка переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN") or (logger.error("TELEGRAM_TOKEN not set") or exit(1))
REDIS_URL = os.getenv("REDIS_URL") or (logger.error("REDIS_URL not set") or exit(1))
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME") or logger.warning("RENDER_EXTERNAL_HOSTNAME not set")

# Подключение к Redis
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Connected to Redis")
except Exception as e:
    logger.error(f"Failed to connect to Redis: {e}")
    raise

subscribed_users = set()
seen_ids = set()

async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    try:
        await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)
        logger.debug(f"Message sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")

def get_settings_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Открыть настройки", web_app={"url": "https://realestatege.netlify.app/"})]])

def save_filters(chat_id: int, filters: dict):
    try:
        redis_client.set(f"filters:{chat_id}", json.dumps(filters))
        logger.info(f"Saved filters for {chat_id}: {filters}")
    except Exception as e:
        logger.error(f"Error saving filters for {chat_id}: {e}")

def load_filters(chat_id: int) -> dict:
    try:
        filters_data = redis_client.get(f"filters:{chat_id}")
        return json.loads(filters_data) if filters_data else {}
    except Exception as e:
        logger.error(f"Error loading filters for {chat_id}: {e}")
        return {}

def save_subscribed_users():
    try:
        redis_client.set("subscribed_users", json.dumps(list(subscribed_users)))
        logger.info(f"Saved subscribed users: {subscribed_users}")
    except Exception as e:
        logger.error(f"Error saving subscribed users: {e}")

def load_subscribed_users():
    try:
        users_data = redis_client.get("subscribed_users")
        return set(json.loads(users_data)) if users_data else set()
    except Exception as e:
        logger.error(f"Error loading subscribed users: {e}")
        return set()

def save_seen_ids():
    try:
        redis_client.set("seen_ids", json.dumps(list(seen_ids)))
        logger.info(f"Saved seen_ids: {len(seen_ids)} entries")
    except Exception as e:
        logger.error(f"Error saving seen_ids: {e}")

def load_seen_ids():
    try:
        ids_data = redis_client.get("seen_ids")
        return set(json.loads(ids_data)) if ids_data else set()
    except Exception as e:
        logger.error(f"Error loading seen_ids: {e}")
        return set()

def parse_myhome(bot, loop):
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
    try:
        for chat_id in subscribed_users:
            filters = load_filters(chat_id)
            defaults = {'city': '1', 'deal_type': 'rent', 'price_from': 100, 'price_to': 2000, 'floor_from': 1, 'floor_to': 30,
                        'rooms_from': 1, 'rooms_to': 5, 'bedrooms_from': 1, 'bedrooms_to': 2, 'own_ads': '1'}
            for key, value in defaults.items():
                filters.setdefault(key, value)

            pr_type = "1" if filters['deal_type'] == "rent" else "2" if filters['deal_type'] == "sale" else "1"
            url = (f"https://www.myhome.ge/ru/s?Keyword=&Owner={filters['own_ads']}&PrTypeID={pr_type}&CityID={filters['city']}"
                   f"&Furnished=&KeywordType=False&Sort=4&PriceFrom={filters['price_from']}&PriceTo={filters['price_to']}"
                   f"&FloorFrom={filters['floor_from']}&FloorTo={filters['floor_to']}&RoomNumFrom={filters['rooms_from']}"
                   f"&RoomNumTo={filters['rooms_to']}&BedroomNumFrom={filters['bedrooms_from']}&BedroomNumTo={filters['bedrooms_to']}")

            for attempt in range(3):
                try:
                    logger.info(f"Fetching page for {chat_id} (attempt {attempt + 1}/3): {url}")
                    response = scraper.get(url, timeout=30)
                    logger.debug(f"Response status: {response.status_code}")
                    response.raise_for_status()

                    if "Just a moment..." in response.text or "Checking your browser" in response.text:
                        logger.warning(f"Cloudflare detected for {chat_id}. Response: {response.text[:200]}")
                        break

                    soup = BeautifulSoup(response.text, 'html.parser')
                    listings = soup.find_all('div', class_='statement-card') or soup.find_all('div', class_='card-container')
                    logger.debug(f"Found {len(listings)} listings with selectors 'statement-card' or 'card-container'")

                    if not listings:
                        logger.info(f"No listings found for {chat_id} with filters: {filters}")
                        logger.debug(f"Page HTML snippet: {response.text[:500]}")
                        break

                    for listing in listings:
                        try:
                            link_tag = listing.find('a', class_='card-container-link')
                            if not link_tag:
                                continue
                            link = "https://www.myhome.ge" + link_tag['href']
                            listing_id = link.split('/')[-1]

                            if listing_id in seen_ids:
                                continue

                            title_tag = listing.find('div', class_='card-title')
                            price_tag = listing.find('div', class_='card-price')
                            location_tag = listing.find('div', class_='card-address')

                            message = (f"Новое объявление:\n"
                                       f"Заголовок: {title_tag.text.strip() if title_tag else 'Без заголовка'}\n"
                                       f"Цена: {price_tag.text.strip() if price_tag else 'Цена не указана'}\n"
                                       f"Местоположение: {location_tag.text.strip() if location_tag else 'Местоположение не указано'}\n"
                                       f"Телефон: Телефон скрыт\n"
                                       f"Ссылка: {link}")
                            logger.info(f"Найдено объявление для {chat_id}: {title_tag.text.strip() if title_tag else 'Без заголовка'}")

                            future = asyncio.run_coroutine_threadsafe(
                                send_message(bot, chat_id, message, get_settings_keyboard()), loop)
                            future.result(timeout=5)

                            seen_ids.add(listing_id)
                            save_seen_ids()

                        except Exception as e:
                            logger.error(f"Ошибка парсинга объявления для {chat_id}: {e}")

                    break
                except Exception as e:
                    logger.error(f"Error loading page for {chat_id} on attempt {attempt + 1}: {e}")
                    time.sleep(random.uniform(5, 10))
                    continue
            else:
                logger.error(f"Failed to load page for {chat_id} after 3 attempts")
    except Exception as e:
        logger.error(f"Failed to parse myhome.ge: {e}")

def run_parser(bot, loop):
    global subscribed_users, seen_ids
    subscribed_users = load_subscribed_users()
    seen_ids = load_seen_ids()
    while True:
        try:
            logger.info("Проверка новых объявлений на myhome.ge...")
            parse_myhome(bot, loop)
        except Exception as e:
            logger.error(f"Error in parser loop: {e}")
        time.sleep(600)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    args = context.args

    if args and args[0].startswith("filters_"):
        params_str = args[0].replace("filters_", "")
        params = dict(param.split("=") for param in params_str.split("&") if "=" in param)
        
        filters = load_filters(chat_id)
        defaults = {'city': filters.get('city', '1'), 'deal_type': filters.get('deal_type', 'rent'),
                    'price_from': filters.get('price_from', 100), 'price_to': filters.get('price_to', 2000),
                    'floor_from': filters.get('floor_from', 1), 'floor_to': filters.get('floor_to', 30),
                    'rooms_from': filters.get('rooms_from', 1), 'rooms_to': filters.get('rooms_to', 5),
                    'bedrooms_from': filters.get('bedrooms_from', 1), 'bedrooms_to': filters.get('bedrooms_to', 2),
                    'own_ads': filters.get('own_ads', '1')}
        
        for key in defaults:
            if key in params:
                filters[key] = params[key] if key in ['city', 'deal_type', 'own_ads'] else int(params[key])
            else:
                filters[key] = defaults[key]

        save_filters(chat_id, filters)
        logger.info(f"User {chat_id} updated filters: {filters}")

        city_name = {"0": "Искать везде", "1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}.get(filters['city'], "Неизвестный город")
        deal_type_name = {"rent": "Аренда", "sale": "Продажа"}.get(filters['deal_type'], "Искать везде")
        own_ads_name = "Да" if filters['own_ads'] == "1" else "Нет"

        await update.message.reply_text(
            f"Фильтры обновлены:\n"
            f"Город: {city_name}\n"
            f"Тип сделки: {deal_type_name}\n"
            f"Цена: от {filters['price_from']} до {filters['price_to']}\n"
            f"Этаж: от {filters['floor_from']} до {filters['floor_to']}\n"
            f"Комнаты: от {filters['rooms_from']} до {filters['rooms_to']}\n"
            f"Спальни: от {filters['bedrooms_from']} до {filters['bedrooms_to']}\n"
            f"Только собственники: {own_ads_name}",
            reply_markup=get_settings_keyboard()
        )
    elif args and args[0].startswith("city_"):
        city_id = args[0].split("_")[1]
        filters = load_filters(chat_id)
        filters["city"] = city_id
        save_filters(chat_id, filters)
        city_name = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}.get(city_id, "Неизвестный город")
        logger.info(f"User {chat_id} set city to {city_id}")
        await update.message.reply_text(f"Город обновлен: {city_name}!", reply_markup=get_settings_keyboard())
    else:
        if chat_id not in subscribed_users:
            await update.message.reply_text(
                "Привет! Я могу рассылать новые объявления об аренде или продаже квартиры.\n\n"
                "Нажми 'Включить бот'.", reply_markup=None)
            return
        logger.info(f"User {chat_id} started the bot")
        await update.message.reply_text(
            "Привет! Я могу рассылать новые объявления об аренде или продаже квартиры.\n\n"
            "Нажми 'Открыть настройки':", reply_markup=get_settings_keyboard())

async def enable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    subscribed_users.add(chat_id)
    save_subscribed_users()
    logger.info(f"User {chat_id} enabled the bot")
    await update.message.reply_text(
        "Бот включен! Теперь ты будешь получать уведомления.\n\nНажми 'Открыть настройки':",
        reply_markup=get_settings_keyboard())

async def disable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    subscribed_users.discard(chat_id)
    save_subscribed_users()
    logger.info(f"User {chat_id} disabled the bot")
    await update.message.reply_text(
        "Бот отключен. Нажми 'Включить бот'.", reply_markup=None)

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id not in subscribed_users:
        await update.message.reply_text("Бот отключен. Нажми 'Включить бот'.", reply_markup=None)
        return
    await update.message.reply_text("Нажми 'Открыть настройки':", reply_markup=get_settings_keyboard())

async def reset_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global seen_ids
    chat_id = update.message.chat_id
    seen_ids.clear()
    try:
        redis_client.delete("seen_ids")
        logger.info(f"User {chat_id} reset seen_ids")
        await update.message.reply_text("Список объявлений сброшен. Бот начнёт парсинг заново.")
    except Exception as e:
        logger.error(f"Error resetting seen_ids for {chat_id}: {e}")
        await update.message.reply_text("Ошибка при сбросе списка.")

async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug(f"Получено обновление: {update.to_dict()}")

def main():
    try:
        application = Application.builder().token(TOKEN).build()
        loop = asyncio.get_event_loop()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("on", enable_bot))
        application.add_handler(CommandHandler("off", disable_bot))
        application.add_handler(CommandHandler("settings", settings))
        application.add_handler(CommandHandler("reset_seen", reset_seen))
        application.add_handler(MessageHandler(filters.ALL, debug_update), group=1)

        parser_thread = threading.Thread(target=run_parser, args=(application.bot, loop))
        parser_thread.daemon = True
        parser_thread.start()

        webhook_url = f"https://{RENDER_HOSTNAME}/{TOKEN}"
        logger.info(f"Setting webhook to {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0", port=10000, url_path=TOKEN, webhook_url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        raise

if __name__ == "__main__":
    main()