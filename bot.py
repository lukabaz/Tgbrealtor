import os
import json
import redis
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler

# Подключение к Redis
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# Настройка вебхука
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"

# Сохранение фильтров в Redis
def save_filters(chat_id: int, filters: dict):
    redis_client.set(f"filters:{chat_id}", json.dumps(filters))

# Сохранение статуса бота в Redis
def save_bot_status(chat_id: int, status: str):
    redis_client.set(f"bot_status:{chat_id}", status)

# Получение статуса бота из Redis
def get_bot_status(chat_id: int) -> str:
    status = redis_client.get(f"bot_status:{chat_id}")
    return status if status else "stopped"

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

# Обновление клавиатуры с учётом статуса бота
def get_settings_keyboard(chat_id: int):
    status = get_bot_status(chat_id)
    status_button = "🟢 Стоп" if status == "running" else "🔴 Старт"
    return ReplyKeyboardMarkup([
        [KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"}), KeyboardButton(status_button)]
    ], resize_keyboard=True)

# Обработчик Web App данных
async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    filters_data = json.loads(update.message.web_app_data.data)
    save_filters(chat_id, filters_data)
    response_message = format_filters_response(filters_data)
    await context.bot.send_message(chat_id=chat_id, text=response_message, reply_markup=get_settings_keyboard(chat_id))

# Обработчик текстовых сообщений для показа клавиатуры
async def show_settings_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text

    if text in ["🟢 Стоп", "🔴 Старт"]:
        status = get_bot_status(chat_id)
        new_status = "stopped" if status == "running" else "running"
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Управление ботом",
            description=f"{'Остановка' if new_status == 'stopped' else 'Запуск'} бота",
            payload=f"toggle_bot_status:{chat_id}:{new_status}",
            provider_token="",  # Для Stars оставляем пустым
            currency="XTR",  # Только Telegram Stars
            prices=[{"label": "Стоимость", "amount": 0}],
            start_parameter="toggle-bot-status"
        )
    else:
        await context.bot.send_message(chat_id=chat_id, text="Настройте фильтры:", reply_markup=get_settings_keyboard(chat_id))

# Обработчик подтверждения оплаты
async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await context.bot.answer_pre_checkout_query(query.id, ok=True)

# Обработчик успешной оплаты
async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    _, chat_id_from_payload, new_status = payload.split(":")
    chat_id_from_payload = int(chat_id_from_payload)

    if chat_id == chat_id_from_payload:
        save_bot_status(chat_id, new_status)
        status_text = "Бот остановлен 🔴" if new_status == "stopped" else "Бот запущен 🟢"
        await context.bot.send_message(
            chat_id=chat_id,
            text=status_text,
            reply_markup=get_settings_keyboard(chat_id)
        )

# Инициализация бота
def main():
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, show_settings_keyboard))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        url_path=os.getenv("TELEGRAM_TOKEN"),
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message", "pre_checkout_query"]
    )

if __name__ == "__main__":
    main()