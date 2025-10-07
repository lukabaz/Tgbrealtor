# authorization/subscription.py
from datetime import datetime, timedelta, timezone
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils.redis_client import redis_client
from utils.logger import logger
from utils.telegram_utils import retry_on_timeout


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
        # Подписка не активна, оставляем Redis-ключ живым 1.2 месяца чтобы не мог использовать триал
        redis_client.expire(f"user:{chat_id}", INACTIVITY_TTL)

    save_user_data(chat_id, user_data)
    # Обновляем множество подписчиков
    if status == "running":
        sub_end = int(user_data.get("subscription_end", "0"))
        if sub_end > int(datetime.now(timezone.utc).timestamp()):
            redis_client.sadd("subscribed_users", chat_id)
            logger.info(f"➕ Added chat_id={chat_id} to subscribed_users")
        else:
            redis_client.srem("subscribed_users", chat_id)
            logger.info(f"➖ Removed chat_id={chat_id} from subscribed_users (subscription expired)")
    else:
        redis_client.srem("subscribed_users", chat_id)
        logger.info(f"➖ Removed chat_id={chat_id} from subscribed_users (status stopped)")

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
        [KeyboardButton("⚙️ Настройки", web_app={"url": "https://realfind.netlify.app"}), KeyboardButton(status_btn)],
        [KeyboardButton("🎁 Бесплатно"), KeyboardButton("💬 Поддержка", web_app={"url": "https://realfind.netlify.app/support"})] 
    ], resize_keyboard=True)

async def send_status_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str):
    async def send():
        return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=get_settings_keyboard(chat_id))
    await retry_on_timeout(send, chat_id=chat_id, message_text=text)

async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if cm.chat.type == "private" and cm.old_chat_member.status == "kicked" and cm.new_chat_member.status == "member":
        welcome_text = "Добро пожаловать! Настройте фильтры и нажмите 🔴 Старт"
        async def send_welcome():
            return await context.bot.send_message(chat_id=cm.chat.id, text=welcome_text, reply_markup=get_settings_keyboard(cm.chat.id))
        await retry_on_timeout(send_welcome, chat_id=cm.chat.id, message_text=welcome_text)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text  # Извлекаем текст из сообщения

    if text == "🔴 Старт":
        if is_subscription_active(chat_id):
            save_bot_status(chat_id, "running")
            start_text = "🔍 Мониторинг активирован! Ждём свежих объявлений."
            async def send_start():
                return await context.bot.send_message(chat_id=chat_id, text=start_text, reply_markup=get_settings_keyboard(chat_id))
            await retry_on_timeout(send_start, chat_id=chat_id, message_text=start_text)
        else:
            invoice_text = "Для активации мониторинга оформите подписку."
            async def send_invoice():
                return await context.bot.send_invoice(
                    chat_id=chat_id,
                    title="Доступ к объявлениям",
                    description="Подписка на 30 дней",
                    payload=f"toggle_bot_status:{chat_id}:stopped",
                    provider_token="",
                    currency="XTR",
                    prices=[{"label": "Стоимость", "amount": 2500}],
                    start_parameter="toggle-bot-status"
                )
            await retry_on_timeout(send_invoice, chat_id=chat_id, message_text=invoice_text)
    elif text == "🟢 Стоп":
        save_bot_status(chat_id, "stopped")
        stop_text = "Подписка истекла 🔴" if not is_subscription_active(chat_id) else "Мониторинг приостановлен 🛑."
        async def send_stop():
            return await context.bot.send_message(chat_id=chat_id, text=stop_text, reply_markup=get_settings_keyboard(chat_id))
        await retry_on_timeout(send_stop, chat_id=chat_id, message_text=stop_text)
    elif text == "🎁 Бесплатно":
            # Сначала проверяем, активна ли уже подписка
            if is_subscription_active(chat_id):
                trial_active_text = "У вас уже есть активная подписка! Бесплатный период можно активировать только после её окончания."
                async def send_trial_active():
                    return await context.bot.send_message(
                        chat_id=chat_id,
                        text=trial_active_text
                    )
                await retry_on_timeout(send_trial_active, chat_id=chat_id, message_text=trial_active_text)
                return
            if redis_client.get(f"trial_used:{chat_id}") == "true":
                trial_used_text = "Вы уже использовали бесплатные 2 дня!"
                async def send_trial_used():
                    return await context.bot.send_message(
                        chat_id=chat_id,
                        text=trial_used_text
                    )
                await retry_on_timeout(send_trial_used, chat_id=chat_id, message_text=trial_used_text)
                async def send_invoice():
                    return await context.bot.send_invoice(
                        chat_id=chat_id,
                        title="Доступ к объявлениям",
                        description="Подписка на 30 дней",
                        payload=f"toggle_bot_status:{chat_id}:stopped",
                        provider_token="",
                        currency="XTR",
                        prices=[{"label": "Стоимость", "amount": 2500}],
                        start_parameter="toggle-bot-status"
                    )
                await retry_on_timeout(send_invoice, chat_id=chat_id, message_text="Для активации мониторинга оформите подписку.")
                return
            # Назначаем бесплатный период
            redis_client.set(f"trial_used:{chat_id}", "true")
            trial_end = datetime.now(timezone.utc) + timedelta(seconds=TRIAL_TTL)
            save_bot_status(chat_id, "stopped", custom_sub_end=trial_end)
            trial_text = "Вам предоставлены 2 дня бесплатного доступа! Подписка активирована 🟢"
            async def send_trial():
                return await context.bot.send_message(
                    chat_id=chat_id,
                    text=trial_text
                )
            await retry_on_timeout(send_trial, chat_id=chat_id, message_text=trial_text)

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
    payment_text = f"Подписка продлена! 🟢\nНовая дата окончания: {formatted_date}"
    async def send_payment():
        return await context.bot.send_message(chat_id=chat_id, text=payment_text, reply_markup=get_settings_keyboard(chat_id))
    await retry_on_timeout(send_payment, chat_id=chat_id, message_text=payment_text) 

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def send_pre_checkout():
        return await context.bot.answer_pre_checkout_query(update.pre_checkout_query.id, ok=True)
    await retry_on_timeout(send_pre_checkout, chat_id=update.pre_checkout_query.from_user.id, message_text="Pre-checkout confirmation")                      