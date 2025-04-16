import os
import logging
import json
import redis
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Подключение к Redis
redis_url = os.getenv("REDIS_URL")
redis_client = redis.from_url(redis_url, decode_responses=True)

# Настройка вебхука
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"

# Асинхронная функция для отправки сообщений
async def send_message(bot, chat_id: int, message: str, reply_markup=None):
    await bot.send_message(chat_id=chat_id, text=message, reply_markup=reply_markup, disable_web_page_preview=True)

# Работа с Redis
def save_filters(chat_id: int, filters: dict):
    try:
        redis_client.set(f"filters:{chat_id}", json.dumps(filters))
        logger.info(f"Filters saved for chat_id {chat_id}: {filters}")
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
    users.add(str(chat_id))
    redis_client.set("subscribed_users", json.dumps(list(users)))

def remove_subscriber(chat_id: int):
    users = get_subscribed_users()
    users.discard(str(chat_id))
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

# Форматирование ответа с параметрами
def format_filters_response(filters, language='ru'):
    city_map = {'1': 'Тбилиси', '2': 'Батуми', '3': 'Кутаиси'}
    deal_type_map = {'rent': 'Аренда', 'sale': 'Продажа'}
    own_ads_map = {'1': 'Да', '0': 'Нет'}

    city = city_map.get(filters.get('city', ''), 'Не указан')
    districts = []
    if filters.get('districts', {}).get('tbilisi'):
        districts.extend(filters['districts']['tbilisi'])
    if filters.get('districts', {}).get('batumi'):
        districts.extend(filters['districts']['batumi'])
    if filters.get('districts', {}).get('kutaisi'):
        districts.extend(filters['districts']['kutaisi'])
    districts_str = ', '.join(districts) if districts else 'Не указаны'
    deal_type = deal_type_map.get(filters.get('deal_type', ''), 'Не указан')
    price = f"{filters.get('price_from', '0')}-{filters.get('price_to', '0')}$"
    floor = f"{filters.get('floor_from', '0')}-{filters.get('floor_to', '0')}"
    rooms = f"{filters.get('rooms_from', '0')}-{filters.get('rooms_to', '0')}"
    bedrooms = f"{filters.get('bedrooms_from', '0')}-{filters.get('bedrooms_to', '0')}"
    own_ads = own_ads_map.get(filters.get('own_ads', '0'), 'Не указан')

    return (
        f"Фильтры сохранены!\n"
        f"Город: {city}\n"
        f"Районы: {districts_str}\n"
        f"Тип сделки: {deal_type}\n"
        f"Цена: {price}\n"
        f"Этаж: {floor}\n"
        f"Комнат: {rooms}\n"
        f"Спален: {bedrooms}\n"
        f"Только собственник: {own_ads}"
    )

# Обработчик вебхука
async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received update: {update.to_dict()}")
    chat_id = update.message.chat_id if update.message else None
    if not chat_id:
        logger.error("No chat_id found in update")
        return

    if update.message and update.message.web_app_data:
        # Обработка данных из Web App
        try:
            filters_data = json.loads(update.message.web_app_data.data)
            logger.info(f"Received Web App data: {filters_data}")
            save_filters(chat_id, filters_data)
            response_message = format_filters_response(filters_data)
            await send_message(context.bot, chat_id, response_message)
        except Exception as e:
            logger.error(f"Error processing web app data: {e}")
            await send_message(context.bot, chat_id, "Ошибка при сохранении фильтров.")
    else:
        logger.info("No web_app_data in update")
        await send_message(context.bot, chat_id, "Пожалуйста, используйте Web App для настройки фильтров.")

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    add_subscriber(chat_id)
    await send_message(context.bot, chat_id, "Добро пожаловать! Вы подписаны на новые объявления.\nИспользуйте /stop для отписки.")

# Команда /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    remove_subscriber(chat_id)
    await send_message(context.bot, chat_id, "Вы отписались от обновлений.")

# Инициализация бота
async def main():
    # Инициализация приложения
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))

    # Настройка вебхука для Telegram
    logger.info(f"Starting webhook server for {WEBHOOK_URL}")
    await application.initialize()
    await application.start()
    await application.updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 10000)),
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message", "web_app_data"]
    )

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()