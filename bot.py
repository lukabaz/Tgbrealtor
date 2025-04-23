import os
import json
import redis
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
from datetime import datetime, timedelta, timezone

redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"
INACTIVITY_TTL = int(1.5 * 30 * 24 * 60 * 60)  # 1.5 месяца
ACTIVE_SUBSCRIPTION_MESSAGE = "Подписка активирована 🟢"

def save_filters(chat_id: int, url: str):
    key = f"filters:{chat_id}"
    redis_client.setex(key, INACTIVITY_TTL, url)

def get_end_of_subscription():
    next_month = (datetime.now(timezone.utc).replace(day=1) + timedelta(days=32)).replace(day=1)
    return int(next_month.timestamp())

def save_bot_status(chat_id: int, status: str, set_sub_end: bool = False):
    status_key = f"bot_status:{chat_id}"
    sub_end_key = f"subscription_end:{chat_id}"

    redis_client.set(status_key, status)

    if set_sub_end:
        end_timestamp = get_end_of_subscription()
        ttl = end_timestamp - int(datetime.now(timezone.utc).timestamp())
        redis_client.setex(sub_end_key, ttl, end_timestamp)
        redis_client.expire(status_key, ttl)
    else:
        redis_client.expire(status_key, INACTIVITY_TTL)

def is_subscription_active(chat_id: int) -> bool:
    ts = redis_client.get(f"subscription_end:{chat_id}")
    return ts and int(ts) > int(datetime.now(timezone.utc).timestamp())

def get_bot_status(chat_id: int) -> str:
    return redis_client.get(f"bot_status:{chat_id}") or "stopped"

def get_settings_keyboard(chat_id: int):
    status = get_bot_status(chat_id)
    status_btn = "🟢 Стоп" if status == "running" else "🔴 Старт"
    return ReplyKeyboardMarkup([
        [KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"}), KeyboardButton(status_btn)]
    ], resize_keyboard=True)

async def send_status_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str):
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=get_settings_keyboard(chat_id))

def format_filters_response(filters):
    city_map = {'1': 'Тбилиси', '2': 'Батуми', '3': 'Кутаиси'}
    deal_type_map = {'rent': 'Аренда', 'sale': 'Продажа'}
    own_ads_map = {'1': 'Да', '0': 'Нет'}

    city = city_map.get(filters.get('city', ''), 'Не указан')
    districts = []
    for city_key in ['tbilisi', 'batumi', 'kutaisi']:
        districts.extend(filters.get('districts', {}).get(city_key, []))
    return (
        f"Фильтры сохранены!\n"
        f"Город: {city}\n"
        f"Районы: {', '.join(districts) if districts else 'Не указаны'}\n"
        f"Тип сделки: {deal_type_map.get(filters.get('deal_type', ''), 'Не указан')}\n"
        f"Цена: {filters.get('price_from', '0')}-{filters.get('price_to', '0')}$\n"
        f"Этаж: {filters.get('floor_from', '0')}-{filters.get('floor_to', '0')}\n"
        f"Комнат: {filters.get('rooms_from', '0')}-{filters.get('rooms_to', '0')}\n"
        f"Спален: {filters.get('bedrooms_from', '0')}-{filters.get('bedrooms_to', '0')}\n"
        f"Только собственник: {own_ads_map.get(filters.get('own_ads', '0'), 'Не указан')}"
    )

async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    filters_data = json.loads(update.message.web_app_data.data)
    print("Текущее UTC время сервера:", datetime.now(timezone.utc))  # ← вот эта строка
    
    if "url" in filters_data:
        save_filters(chat_id, filters_data["url"])  # Сохраняем только URL

        # Сохраняем метку времени сохранения фильтров в формате UTC
        redis_client.setex(
            f"filters_timestamp:{chat_id}",
            INACTIVITY_TTL,
            int(datetime.now(timezone.utc).timestamp())
        )

        await send_status_message(chat_id, context, format_filters_response(filters_data))
    else:
        await send_status_message(chat_id, context, "Ошибка: URL не сформирован")

async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if cm.chat.type == "private" and cm.old_chat_member.status == "kicked" and cm.new_chat_member.status == "member":
        await send_status_message(cm.chat.id, context, "Добро пожаловать! Настройте фильтры или запустите бота:")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text

    if text in ["🔴 Старт", "🟢 Стоп"]:
        is_starting = text == "🔴 Старт"
        if is_starting:
            if is_subscription_active(chat_id):
                save_bot_status(chat_id, "running")
                await send_status_message(chat_id, context, ACTIVE_SUBSCRIPTION_MESSAGE)
            else:
                # Вместо инвойса сразу активируем подписку
                save_bot_status(chat_id, "running", set_sub_end=True)
                await send_status_message(chat_id, context, ACTIVE_SUBSCRIPTION_MESSAGE)
                #await context.bot.send_invoice(
                    #chat_id=chat_id,
                    #title="Доступ к объявлениям",
                    #description="Подписка на месяц",
                    #payload=f"toggle_bot_status:{chat_id}:running",
                    #provider_token="",
                    #currency="XTR",
                    #prices=[{"label": "Стоимость", "amount": 100}],
                    #start_parameter="toggle-bot-status"
                #)
        else:
            save_bot_status(chat_id, "stopped")
            message = "Подписка истекла 🔴" if not is_subscription_active(chat_id) else "Бот остановлен 🛑."
            await send_status_message(chat_id, context, message)

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.answer_pre_checkout_query(update.pre_checkout_query.id, ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _, payload_chat_id, new_status = update.message.successful_payment.invoice_payload.split(":")
    if chat_id == int(payload_chat_id):
        save_bot_status(chat_id, new_status, set_sub_end=True)
        await send_status_message(chat_id, context, ACTIVE_SUBSCRIPTION_MESSAGE)

def main():
    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    app.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    #app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    #app.add_handler(PreCheckoutQueryHandler(pre_checkout))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        url_path=os.getenv("TELEGRAM_TOKEN"),
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
    )

if __name__ == "__main__":
    main()