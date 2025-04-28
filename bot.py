import os
import json
import redis
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
from datetime import datetime, timedelta, timezone
import logging

known_buttons = {"🔴 Старт","🟢 Стоп","🎁 Бесплатно","⚙️ Настройки","💬 Поддержка"}

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # скрываем подробные логи httpx
logger = logging.getLogger(__name__)

redis_client = redis.from_url(os.getenv("REDIS_URL"), decode_responses=True)
WEBHOOK_URL = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{os.getenv('TELEGRAM_TOKEN')}"
INACTIVITY_TTL = int(1.5 * 30 * 24 * 60 * 60)  # 1.5 месяца
TRIAL_TTL = 2 * 24 * 60 * 60  # 48 часов
ACTIVE_SUBSCRIPTION_MESSAGE = "Подписка активирована 🟢"

def save_user_data(chat_id: int, data: dict):
    redis_client.hset(f"user:{chat_id}", mapping=data)
    redis_client.expire(f"user:{chat_id}", INACTIVITY_TTL)

def get_user_data(chat_id: int):
    return redis_client.hgetall(f"user:{chat_id}")

def get_end_of_subscription():
    subscription_end = datetime.now(timezone.utc) + timedelta(days=30)
    return int(subscription_end.timestamp())

def save_bot_status(chat_id: int, status: str, set_sub_end: bool = False):
    user_data = get_user_data(chat_id)
    user_data['bot_status'] = status

    if set_sub_end:
        end_timestamp = get_end_of_subscription()
        ttl = end_timestamp - int(datetime.now(timezone.utc).timestamp())
        user_data['subscription_end'] = str(end_timestamp)
        redis_client.expire(f"user:{chat_id}", ttl)
    else:
        redis_client.expire(f"user:{chat_id}", INACTIVITY_TTL)

    save_user_data(chat_id, user_data)

def is_subscription_active(chat_id: int) -> bool:
    user_data = get_user_data(chat_id)
    ts = user_data.get('subscription_end')
    return ts and int(ts) > int(datetime.now(timezone.utc).timestamp())

def get_bot_status(chat_id: int) -> str:
    user_data = get_user_data(chat_id)
    return user_data.get('bot_status', "stopped")

def get_settings_keyboard(chat_id: int):
    status = get_bot_status(chat_id)
    status_btn = "🟢 Стоп" if status == "running" else "🔴 Старт"
    return ReplyKeyboardMarkup([
        [KeyboardButton("⚙️ Настройки", web_app={"url": "https://realestatege.netlify.app"}), KeyboardButton(status_btn)],
        [KeyboardButton("🎁 Бесплатно"), KeyboardButton("💬 Поддержка", web_app={"url": "https://realestatege.netlify.app/support"})] 
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

    if "url" in filters_data:
        save_user_data(chat_id, {"filters_url": filters_data["url"]})  # Сохраняем только URL
        utc_timestamp = int(datetime.now(timezone.utc).timestamp())
        logger.info("💾 Saving filters_timestamp as: %s (UTC)", utc_timestamp)

        save_user_data(chat_id, {"filters_timestamp": str(utc_timestamp)})
        await send_status_message(chat_id, context, format_filters_response(filters_data))

    elif "supportMessage" in filters_data:
        message = filters_data["supportMessage"]
        await context.bot.send_message('6770986953', f"📩 Поддержка от {chat_id}:\n{message}")
        await context.bot.send_message(chat_id, "✅ Ваше сообщение отправлено в поддержку.")    
    else:
        await send_status_message(chat_id, context, "Ошибка: URL не сформирован")

async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if cm.chat.type == "private" and cm.old_chat_member.status == "kicked" and cm.new_chat_member.status == "member":
        await send_status_message(cm.chat.id, context, "Добро пожаловать! Настройте фильтры и нажмите 🔴 Старт")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text  # Извлекаем текст из сообщения

    if text == "🔴 Старт":
        if is_subscription_active(chat_id):
            save_bot_status(chat_id, "running")
            await send_status_message(chat_id, context, "🔍 Мониторинг активирован! Ждём свежих объявлений.")
        else:
            await context.bot.send_invoice(
                chat_id=chat_id,
                title="Доступ к объявлениям",
                description="Подписка на месяц",
                payload=f"toggle_bot_status:{chat_id}:running",
                provider_token="",
                currency="XTR",
                prices=[{"label": "Стоимость", "amount": 250}],
                start_parameter="toggle-bot-status"
            )
    elif text == "🟢 Стоп":
        save_bot_status(chat_id, "stopped")
        message = "Подписка истекла 🔴" if not is_subscription_active(chat_id) else "Мониторинг приостановлен 🛑."
        await send_status_message(chat_id, context, message)

    elif text == "🎁 Бесплатно":
            # Сначала проверяем, активна ли уже подписка
            if is_subscription_active(chat_id):
                await context.bot.send_message(chat_id, "У вас уже есть активная подписка! Бесплатный период можно активировать только после её окончания.")
            if redis_client.get(f"trial_used:{chat_id}") == "true":
                await context.bot.send_message(chat_id, "Вы уже использовали бесплатные 2 дня!")
                await context.bot.send_invoice(
                    chat_id=chat_id,
                    title="Доступ к объявлениям",
                    description="Подписка на месяц",
                    payload=f"toggle_bot_status:{chat_id}:running",
                    provider_token="",
                    currency="XTR",
                    prices=[{"label": "Стоимость", "amount": 250}],
                    start_parameter="toggle-bot-status"
                )
            else:
                redis_client.set(f"trial_used:{chat_id}", "true")
                end_of_subscription = int((datetime.now(timezone.utc) + timedelta(seconds=TRIAL_TTL)).timestamp())
                save_user_data(chat_id, {"subscription_end": str(end_of_subscription)})
                save_bot_status(chat_id, "running", set_sub_end=True)
                await context.bot.send_message(chat_id, "Вам предоставлены 2 дня бесплатного доступа! Подписка активирована 🟢")

async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    message_text = update.message.text

    if message_text in known_buttons:
        return

    await context.bot.send_message(chat_id, "❗Для обращения нажмите на панели меню кнопку Поддержка.")

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    response = "Мы получили ваш запрос и работаем над решением. Спасибо за терпение."
    await context.bot.send_message(chat_id, response)

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
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))  # Для запроса от пользователя
    
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        url_path=os.getenv("TELEGRAM_TOKEN"),
        webhook_url=WEBHOOK_URL,
        allowed_updates=["message", "pre_checkout_query", "my_chat_member"]
    )

if __name__ == "__main__":
    main()