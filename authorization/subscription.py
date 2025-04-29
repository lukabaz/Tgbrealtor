from datetime import datetime, timedelta, timezone
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils.redis_client import redis_client


INACTIVITY_TTL = int(1.2 * 30 * 24 * 60 * 60)  # 1.2 месяца
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

def save_bot_status(chat_id: int, status: str, set_sub_end: bool = False, custom_sub_end: datetime | None = None):
    user_data = get_user_data(chat_id)
    user_data['bot_status'] = status

    if custom_sub_end:
        end_timestamp = int(custom_sub_end.timestamp())
        ttl = end_timestamp - int(datetime.now(timezone.utc).timestamp())
        user_data['subscription_end'] = str(end_timestamp)
        redis_client.expire(f"user:{chat_id}", ttl)
    elif set_sub_end:
        end_timestamp = get_end_of_subscription()
        ttl = end_timestamp - int(datetime.now(timezone.utc).timestamp())
        user_data['subscription_end'] = str(end_timestamp)
        redis_client.expire(f"user:{chat_id}", ttl)
    else:
        # Подписка не активна, оставляем Redis-ключ живым 1.2 месяца
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
                description="Подписка на 30 дней",
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
                return
            if redis_client.get(f"trial_used:{chat_id}") == "true":
                await context.bot.send_message(chat_id, "Вы уже использовали бесплатные 2 дня!")
                await context.bot.send_invoice(
                    chat_id=chat_id,
                    title="Доступ к объявлениям",
                    description="Подписка на 30 дней",
                    payload=f"toggle_bot_status:{chat_id}:running",
                    provider_token="",
                    currency="XTR",
                    prices=[{"label": "Стоимость", "amount": 250}],
                    start_parameter="toggle-bot-status"
                )
                return
            # Назначаем бесплатный период
            redis_client.set(f"trial_used:{chat_id}", "true")
            trial_end = datetime.now(timezone.utc) + timedelta(seconds=TRIAL_TTL)
            save_bot_status(chat_id, "running", custom_sub_end=trial_end)
            await context.bot.send_message(chat_id, "Вам предоставлены 2 дня бесплатного доступа! Подписка активирована 🟢")

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _, payload_chat_id, new_status = update.message.successful_payment.invoice_payload.split(":")
    
    if chat_id != int(payload_chat_id):
        return

    # Получаем текущую дату окончания подписки, если есть
    user_data = get_user_data(chat_id)
    now = datetime.now(timezone.utc)

    current_end_ts = int(user_data.get("subscription_end", "0"))
    current_end = datetime.fromtimestamp(current_end_ts, tz=timezone.utc)

    # Если подписка уже активна — продлеваем от конца, иначе — от текущего момента
    if current_end > now:
        new_end = current_end + timedelta(days=30)
    else:
        new_end = now + timedelta(days=30)

    # Обновляем статус и срок подписки централизованно
    save_bot_status(chat_id, new_status, custom_sub_end=new_end)

    # Форматируем дату
    formatted_date = new_end.strftime("%d-%m-%Y %H:%M")

    # Отправляем сообщение
    await send_status_message(chat_id, context, f"Подписка продлена! 🟢\nНовая дата окончания: {formatted_date}") 

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.answer_pre_checkout_query(update.pre_checkout_query.id, ok=True)                      