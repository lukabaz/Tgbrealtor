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
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Подключение к Redis
redis_url = os.getenv("REDIS_URL")
redis_client = redis.from_url(redis_url, decode_responses=True)

# Список пользователей, которые подписались на уведомления
subscribed_users = set()

# Хранилище ID объявлений, чтобы не дублировать
seen_ids = set()

# Асинхронная функция для отправки сообщений в Telegram
async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)

# Создание клавиатуры для открытия Web App
def get_settings_keyboard():
    keyboard = [
        [InlineKeyboardButton("Открыть настройки", web_app={"url": "https://realestatege.netlify.app/"})]
    ]
    return InlineKeyboardMarkup(keyboard)

# Сохранение фильтров в Redis
def save_filters(chat_id: int, filters: dict):
    try:
        redis_client.set(f"filters:{chat_id}", json.dumps(filters))
        logger.info(f"Saved filters for chat {chat_id}: {filters}")
    except Exception as e:
        logger.error(f"Error saving filters for chat {chat_id}: {e}")

# Загрузка фильтров из Redis
def load_filters(chat_id: int) -> dict:
    try:
        filters_data = redis_client.get(f"filters:{chat_id}")
        if filters_data:
            return json.loads(filters_data)
        return {}
    except Exception as e:
        logger.error(f"Error loading filters for chat {chat_id}: {e}")
        return {}

# Сохранение подписанных пользователей в Redis
def save_subscribed_users():
    try:
        redis_client.set("subscribed_users", json.dumps(list(subscribed_users)))
        logger.info(f"Saved subscribed users: {subscribed_users}")
    except Exception as e:
        logger.error(f"Error saving subscribed users: {e}")

# Загрузка подписанных пользователей из Redis
def load_subscribed_users():
    try:
        users_data = redis_client.get("subscribed_users")
        if users_data:
            return set(json.loads(users_data))
        return set()
    except Exception as e:
        logger.error(f"Error loading subscribed users: {e}")
        return set()

# Сохранение seen_ids в Redis
def save_seen_ids():
    try:
        redis_client.set("seen_ids", json.dumps(list(seen_ids)))
        logger.info(f"Saved seen_ids: {len(seen_ids)} entries")
    except Exception as e:
        logger.error(f"Error saving seen_ids: {e}")

# Загрузка seen_ids из Redis
def load_seen_ids():
    try:
        ids_data = redis_client.get("seen_ids")
        if ids_data:
            return set(json.loads(ids_data))
        return set()
    except Exception as e:
        logger.error(f"Error loading seen_ids: {e}")
        return set()

# Настройка Selenium WebDriver
def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Запуск в фоновом режиме
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    try:
        # Используем webdriver_manager без указания версии
        driver_path = ChromeDriverManager(driver_version="114.0.5735.90").install()
        logger.info(f"ChromeDriver installed at: {driver_path}")
        driver = webdriver.Chrome(service=Service(driver_path), options=chrome_options)
        logger.info("Selenium WebDriver initialized successfully")
        return driver
    except Exception as e:
        logger.error(f"Failed to setup ChromeDriver with webdriver_manager: {e}")
        raise

# Функция парсинга объявлений с учетом фильтров
def parse_myhome(bot, loop):
    try:
        driver = setup_driver()
    except Exception as e:
        logger.error(f"Failed to setup Selenium driver: {e}")
        return  # Пропускаем парсинг, если драйвер не запустился

    try:
        for chat_id in subscribed_users:
            filters = load_filters(chat_id)
            city = filters.get("city", "1")  # По умолчанию Тбилиси
            deal_type = filters.get("deal_type", "0")  # 0 - Искать везде, rent - Аренда, sale - Продажа
            price_from = filters.get("price_from", 100)
            price_to = filters.get("price_to", 2000)
            floor_from = filters.get("floor_from", 1)
            floor_to = filters.get("floor_to", 30)
            rooms_from = filters.get("rooms_from", 1)
            rooms_to = filters.get("rooms_to", 5)
            bedrooms_from = filters.get("bedrooms_from", 1)
            bedrooms_to = filters.get("bedrooms_to", 2)
            own_ads = filters.get("own_ads", "1")  # По умолчанию только собственники

            # Формируем URL с фильтрами
            pr_type = ""
            if deal_type == "rent":
                pr_type = "1"  # Аренда
            elif deal_type == "sale":
                pr_type = "2"  # Продажа

            url = (
                f"https://www.myhome.ge/ru/s?Keyword=&Owner={own_ads}&PrTypeID={pr_type}&CityID={city}&Furnished=&KeywordType=False&Sort=4"
                f"&PriceFrom={price_from}&PriceTo={price_to}"
                f"&FloorFrom={floor_from}&FloorTo={floor_to}"
                f"&RoomNumFrom={rooms_from}&RoomNumTo={rooms_to}"
                f"&BedroomNumFrom={bedrooms_from}&BedroomNumTo={bedrooms_to}"
            )

            try:
                logger.info(f"Fetching page for chat {chat_id}: {url}")
                driver.get(url)
                # Даём время на загрузку страницы и выполнение JavaScript (увеличиваем время для Cloudflare)
                time.sleep(10)

                # Получаем HTML-код страницы
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                listings = soup.find_all('div', class_='statement-card')

                if not listings:
                    logger.warning(f"No listings found for chat {chat_id}. Page may not have loaded correctly.")
                    continue

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

                        # Телефон (пока заглушка)
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
                            send_message(bot, chat_id, message, get_settings_keyboard()),
                            loop
                        )
                        try:
                            future.result(timeout=5)
                            logger.debug(f"Message sent to {chat_id}")
                        except Exception as e:
                            logger.error(f"Failed to send message to {chat_id}: {e}")

                        seen_ids.add(listing_id)
                        save_seen_ids()

                    except Exception as e:
                        logger.error(f"Ошибка парсинга объявления для chat {chat_id}: {e}")

            except Exception as e:
                logger.error(f"Ошибка при загрузке страницы для chat {chat_id}: {e}")

    finally:
        driver.quit()

# Функция периодического парсинга
def run_parser(bot, loop):
    global subscribed_users, seen_ids
    # Загружаем данные из Redis при старте
    subscribed_users = load_subscribed_users()
    seen_ids = load_seen_ids()
    while True:
        try:
            logger.info("Проверка новых объявлений на myhome.ge...")
            parse_myhome(bot, loop)
        except Exception as e:
            logger.error(f"Error in parser loop: {e}")
        time.sleep(300)  # Проверка каждые 5 минут

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    args = context.args  # Получаем параметры из deep link

    if args and args[0].startswith("filters_"):
        # Извлекаем фильтры из deep link
        params_str = args[0].replace("filters_", "")
        params = dict(param.split("=") for param in params_str.split("&"))
        
        filters = load_filters(chat_id)
        filters["city"] = params.get("city", "1")
        filters["deal_type"] = params.get("deal_type", "0")
        filters["price_from"] = int(params.get("price_from", 100))
        filters["price_to"] = int(params.get("price_to", 2000))
        filters["floor_from"] = int(params.get("floor_from", 1))
        filters["floor_to"] = int(params.get("floor_to", 30))
        filters["rooms_from"] = int(params.get("rooms_from", 1))
        filters["rooms_to"] = int(params.get("rooms_to", 5))
        filters["bedrooms_from"] = int(params.get("bedrooms_from", 1))
        filters["bedrooms_to"] = int(params.get("bedrooms_to", 2))
        filters["own_ads"] = params.get("own_ads", "1")
        
        save_filters(chat_id, filters)
        logger.info(f"User {chat_id} updated filters via deep link: {filters}")

        city_name = {"0": "Искать везде", "1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}.get(filters["city"], "Неизвестный город")
        deal_type_name = {"0": "Искать везде", "rent": "Аренда", "sale": "Продажа"}.get(filters["deal_type"], "Неизвестный тип")
        own_ads_name = "Да" if filters["own_ads"] == "1" else "Нет"

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
        # Обработка старого формата (только город)
        city_id = args[0].split("_")[1]
        filters = load_filters(chat_id)
        filters["city"] = city_id
        save_filters(chat_id, filters)
        city_name = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}.get(city_id, "Неизвестный город")
        logger.info(f"User {chat_id} set city to {city_id} via deep link")
        await update.message.reply_text(
            f"Город обновлен: {city_name}!",
            reply_markup=get_settings_keyboard()
        )
    else:
        if chat_id not in subscribed_users:
            await update.message.reply_text(
                "Привет! Я могу рассылать новые объявления об аренде или продаже квартиры, если они подходят под твой фильтр.\n\n"
                "Нажми 'Включить бот', чтобы начать получать уведомления.",
                reply_markup=None
            )
            return
        logger.info(f"User {chat_id} started the bot")
        await update.message.reply_text(
            "Привет! Я могу рассылать новые объявления об аренде или продаже квартиры, если они подходят под твой фильтр.\n\n"
            "Нажми 'Открыть настройки', чтобы настроить фильтры:",
            reply_markup=get_settings_keyboard()
        )

# Команда /on
async def enable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    subscribed_users.add(chat_id)
    save_subscribed_users()
    logger.info(f"User {chat_id} enabled the bot")
    await update.message.reply_text(
        "Бот включен! Теперь ты будешь получать уведомления о новых объявлениях.\n\n"
        "Нажми 'Открыть настройки', чтобы настроить фильтры:",
        reply_markup=get_settings_keyboard()
    )

# Команда /off
async def disable_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    subscribed_users.discard(chat_id)
    save_subscribed_users()
    logger.info(f"User {chat_id} disabled the bot")
    await update.message.reply_text(
        "Бот отключен. Ты больше не будешь получать уведомления.\n\n"
        "Нажми 'Включить бот', чтобы снова начать получать уведомления.",
        reply_markup=None
    )

# Команда /settings
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if chat_id not in subscribed_users:
        await update.message.reply_text(
            "Бот отключен. Нажми 'Включить бот', чтобы начать получать уведомления.",
            reply_markup=None
        )
        return
    await update.message.reply_text(
        "Нажми 'Открыть настройки', чтобы настроить фильтры:",
        reply_markup=get_settings_keyboard()
    )

# Обработчик всех обновлений для отладки
async def debug_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug(f"Получено обновление: {update.to_dict()}")

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()

    # Получаем цикл событий
    loop = asyncio.get_event_loop()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("on", enable_bot))
    application.add_handler(CommandHandler("off", disable_bot))
    application.add_handler(CommandHandler("settings", settings))
    # Добавляем обработчик для всех обновлений
    application.add_handler(MessageHandler(filters.ALL, debug_update), group=1)

    # Запуск парсера в отдельном потоке
    parser_thread = threading.Thread(target=run_parser, args=(application.bot, loop))
    parser_thread.daemon = True
    parser_thread.start()

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