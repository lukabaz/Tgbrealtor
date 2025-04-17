import os
import json
import redis
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# Подключение к Redis
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# Настройка вебхука
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"

# Сохранение фильтров в Redis
def save_filters(chat_id: int, filters: dict):
    redis_client.set(f"filters:{chat_id}", json.dumps(filters))

# Форматирование ответа с фильтрами
def format_filters_response(filters):
    city_map = {'1': 'Тбилиси', '2': 'Батуми', '3': 'Кутаиси'}
    deal_type_map = {'rent': 'Аренда', 'sale': 'Продажа'}
    own_ads_map = {'1': 'Да', '0': 'Нет'}

    city = city_map.get(filters.get('city', ''), 'Не указан')
    districts = []
    for city_key in ['tbilisi', 'batumi', 'kutaisi']:
        if filters.get('districts', {}).get(city_key):
            districts.extend(filters['districts'][city_key])
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

# Обработчик Web App данных
async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    filters_data = json.loads(update.message.web_app_data.data)
    save_filters(chat_id, filters_data)
    response_message = format_filters_response(filters_data)
    await context.bot.send_message(chat_id=chat_id, text=response_message, reply_markup=get_settings_keyboard())

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    keyboard = [[KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"})]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await context.bot.send_message(chat_id=chat_id, text="Добро пожаловать! Настройте фильтры:", reply_markup=reply_markup)

# Команда /stop
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    await context.bot.send_message(chat_id=chat_id, text="Вы отписались от обновлений.")

# Клавиатура с кнопкой для Web App
def get_settings_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"})]], resize_keyboard=True)

# Инициализация бота
def main():
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        url_path=os.getenv("TELEGRAM_TOKEN"),
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message"]
    )

if __name__ == "__main__":
    main()