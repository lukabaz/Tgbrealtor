import os
import json
import redis
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
from datetime import datetime, timedelta

# Подключение к Redis
redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)

# Настройка вебхука
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"

# Время неактивности (1.5 месяца в секундах)
INACTIVITY_TTL = int(1.5 * 30 * 24 * 60 * 60)  # 1.5 месяца

# Сохранение фильтров в Redis
def save_filters(chat_id: int, filters: dict):
    key = f"filters:{chat_id}"
    redis_client.set(key, json.dumps(filters))
    redis_client.expire(key, INACTIVITY_TTL)

# Вычисление времени до 1 числа следующего месяца
def get_end_of_subscription():
    now = datetime.utcnow()
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return int(next_month.timestamp())

# Сохранение статуса и срока подписки
def save_bot_status(chat_id: int, status: str, set_subscription_end: bool = False):
    key = f"bot_status:{chat_id}"
    sub_end_key = f"subscription_end:{chat_id}"
    
    redis_client.set(key, status)
    if set_subscription_end:
        end_timestamp = get_end_of_subscription()
        redis_client.set(sub_end_key, end_timestamp)
        ttl = int(end_timestamp - datetime.utcnow().timestamp())
        redis_client.expire(key, ttl)
        redis_client.expire(sub_end_key, ttl)
    else:
        ttl = redis_client.ttl(key)
        if ttl > 0:
            redis_client.expire(key, ttl)
        else:
            redis_client.expire(key, INACTIVITY_TTL)
        redis_client.expire(sub_end_key, max(ttl, INACTIVITY_TTL) if redis_client.exists(sub_end_key) else INACTIVITY_TTL)

# Проверка, активна ли подписка
def is_subscription_active(chat_id: int) -> bool:
    sub_end_key = f"subscription_end:{chat_id}"
    end_timestamp = redis_client.get(sub_end_key)
    if end_timestamp:
        end_timestamp = int(end_timestamp)
        current_timestamp = int(datetime.utcnow().timestamp())
        return current_timestamp < end_timestamp
    return False

# Получение статуса бота из Redis
def get_bot_status(chat_id: int) -> str:
    status = redis_client.get(f"bot_status:{chat_id}")
    return status if status else "stopped"

# Обновление клавиатуры с учётом статуса бота
def get_settings_keyboard(chat_id: int):
    status = get_bot_status(chat_id)
    status_button = "🟢 Стоп" if status == "running" else "🔴 Старт"
    return ReplyKeyboardMarkup([
        [KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"}), KeyboardButton(status_button)]
    ], resize_keyboard=True)

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
    await context.bot.send_message(chat_id=chat_id, text=response_message, reply_markup=get_settings_keyboard(chat_id))

# Обработчик для приветственного сообщения в личных чатах
async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_member_update = update.my_chat_member
    if chat_member_update.chat.type == "private" and chat_member_update.old_chat_member.status == "kicked" and chat_member_update.new_chat_member.status == "member":
        chat_id = chat_member_update.chat.id
        await context.bot.send_message(chat_id=chat_id, text="Добро пожаловать! Настройте фильтры или запустите бота:", reply_markup=get_settings_keyboard(chat_id))

# Обработчик текстовых сообщений для управления ботом
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text

    if text == "🔴 Старт":
        status = get_bot_status(chat_id)
        if status == "running":
            await context.bot.send_message(
                chat_id=chat_id,
                text="Подписка уже активна 🟢",
                reply_markup=get_settings_keyboard(chat_id)
            )
        elif is_subscription_active(chat_id):
            save_bot_status(chat_id, "running")
            await context.bot.send_message(
                chat_id=chat_id,
                text="Подписка возобновлена 🟢",
                reply_markup=get_settings_keyboard(chat_id)
            )
        else:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title="Подписка на месяц",
                description="Запуск бота на месяц",
                payload=f"toggle_bot_status:{chat_id}:running",
                provider_token="",
                currency="XTR",
                prices=[{"label": "Стоимость", "amount": 100}],
                start_parameter="toggle-bot-status"
            )
    elif text == "🟢 Стоп":
        save_bot_status(chat_id, "stopped")
        if is_subscription_active(chat_id):
            await context.bot.send_message(
                chat_id=chat_id,
                text="Подписка приостановлена 🔴. Вы можете возобновить её до 1 числа следующего месяца.",
                reply_markup=get_settings_keyboard(chat_id)
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Подписка истекла 🔴",
                reply_markup=get_settings_keyboard(chat_id)
            )

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
        save_bot_status(chat_id, new_status, set_subscription_end=True)
        status_text = "Подписка истекла 🔴" if new_status == "stopped" else "Подписка активна 🟢 до 1 числа следующего месяца"
        await context.bot.send_message(
            chat_id=chat_id,
            text=status_text,
            reply_markup=get_settings_keyboard(chat_id)
        )

# Инициализация бота
def main():
    application = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        url_path=os.getenv("TELEGRAM_TOKEN"),
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
    )

if __name__ == "__main__":
    main()