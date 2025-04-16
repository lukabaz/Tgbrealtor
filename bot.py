import os
import logging
import json
import redis
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Токен от BotFather
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Подключение к Redis
redis_url = os.getenv("REDIS_URL")
redis_client = redis.from_url(redis_url, decode_responses=True)

# Асинхронная функция для отправки сообщений
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

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    add_subscriber(chat_id)
    await update.message.reply_text(
        "Добро пожаловать! Вы подписаны на новые объявления.\nИспользуйте /stop для отписки.",
        reply_markup=get_settings_keyboard()
    )

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