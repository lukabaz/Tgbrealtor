# authorization/subscription.py
from datetime import datetime, timedelta, timezone
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils.redis_client import redis_client
from utils.logger import logger
from utils.telegram_utils import retry_on_timeout
from utils.translations import translations  # Импортируем переводы


INACTIVITY_TTL = int(1.2 * 30 * 24 * 60 * 60)  # 1.2 месяца
TRIAL_TTL = 2 * 24 * 60 * 60  # 48 часов
#ACTIVE_SUBSCRIPTION_MESSAGE = "Подписка активирована 🟢"

def save_user_data(chat_id: int, data: dict):
    redis_client.hset(f"user:{chat_id}", mapping=data)
    #redis_client.expire(f"user:{chat_id}", INACTIVITY_TTL) # перенесли в вебхук

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

def get_user_language(update: Update, user_data: dict) -> str:
    # Приоритет: язык из Redis (WebApp) → language_code → английский
    lang = user_data.get('language', update.effective_user.language_code[:2])
    logger.info(f"Selected language for chat_id={update.effective_chat.id}: {lang}")
    return lang if lang in ['ru', 'en'] else 'en'


def get_settings_keyboard(chat_id: int, lang: str):
    status = get_bot_status(chat_id)
    status_btn = translations['stop_button'][lang] if status == "running" else translations['start_button'][lang]
    return ReplyKeyboardMarkup([
        [KeyboardButton(translations['settings_button'][lang], web_app={"url": "https://realfind.netlify.app"}), KeyboardButton(status_btn)],
        [KeyboardButton(translations['free_button'][lang]), KeyboardButton(translations['support_button'][lang], web_app={"url": "https://realfind.netlify.app/support"})] 
    ], resize_keyboard=True)

async def send_status_message(chat_id: int, context: ContextTypes.DEFAULT_TYPE, text: str, lang: str):
    async def send():
        return await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=get_settings_keyboard(chat_id, lang))
    await retry_on_timeout(send, chat_id=chat_id, message_text=text)

async def welcome_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cm = update.my_chat_member
    if cm.chat.type == "private" and cm.new_chat_member.status == "member":
        user_data = get_user_data(cm.chat.id)
        lang = get_user_language(update, user_data)
        welcome_text = translations['welcome'][lang]
        async def send_welcome():
            return await context.bot.send_message(chat_id=cm.chat.id, text=welcome_text, reply_markup=get_settings_keyboard(cm.chat.id, lang))
        await retry_on_timeout(send_welcome, chat_id=cm.chat.id, message_text=welcome_text)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    text = update.message.text
    user_data = get_user_data(chat_id)
    lang = get_user_language(update, user_data)

    if text in [translations['start_button']['ru'], translations['start_button']['en']]:
        if is_subscription_active(chat_id):
            save_bot_status(chat_id, "running")
            await context.application.subscription_manager.refresh_subscriptions(source="all")
            #logger.info(f"🔄 Skipped cache refresh for chat_id={chat_id} (subscription_manager not verified)") # 08.10
            logger.info(f"🔄 Cache refreshed after start for chat_id={chat_id}") 
            start_text = translations['start'][lang]
            await send_status_message(chat_id, context, start_text, lang)
        else:
            invoice_text = translations['invoice'][lang]
            async def send_invoice():
                return await context.bot.send_invoice(
                    chat_id=chat_id,
                    title=translations['invoice_title'][lang],
                    description=translations['invoice_description'][lang],
                    payload=f"toggle_bot_status:{chat_id}:stopped",
                    provider_token="",
                    currency="XTR",
                    prices=[{"label": translations['invoice_label'][lang], "amount": 2500}],
                    start_parameter="toggle-bot-status"
                )
            await retry_on_timeout(send_invoice, chat_id=chat_id, message_text=invoice_text)
    elif text in [translations['stop_button']['ru'], translations['stop_button']['en']]:
        save_bot_status(chat_id, "stopped")
        await context.application.subscription_manager.refresh_subscriptions(source="all")
        #logger.info(f"🔄 Skipped cache refresh for chat_id={chat_id} (subscription_manager not verified)") # 08.10
        logger.info(f"🔄 Cache refreshed after stop for chat_id={chat_id}")
        stop_text = translations['stop_expired'][lang] if not is_subscription_active(chat_id) else translations['stop'][lang]
        await send_status_message(chat_id, context, stop_text, lang)
    elif text in [translations['free_button']['ru'], translations['free_button']['en']]:
        if is_subscription_active(chat_id):
            trial_active_text = translations['trial_active'][lang]
            async def send_trial_active():
                return await context.bot.send_message(chat_id=chat_id, text=trial_active_text)
            await retry_on_timeout(send_trial_active, chat_id=chat_id, message_text=trial_active_text)
            return
        if redis_client.get(f"trial_used:{chat_id}") == "true":
            trial_used_text = translations['trial_used'][lang]
            async def send_trial_used():
                return await context.bot.send_message(chat_id=chat_id, text=trial_used_text)
            await retry_on_timeout(send_trial_used, chat_id=chat_id, message_text=trial_used_text)
            async def send_invoice():
                return await context.bot.send_invoice(
                    chat_id=chat_id,
                    title=translations['invoice_title'][lang],
                    description=translations['invoice_description'][lang],
                    payload=f"toggle_bot_status:{chat_id}:stopped",
                    provider_token="",
                    currency="XTR",
                    prices=[{"label": translations['invoice_label'][lang], "amount": 2500}],
                    start_parameter="toggle-bot-status"
                )
            await retry_on_timeout(send_invoice, chat_id=chat_id, message_text=translations['invoice'][lang])
            return
        redis_client.set(f"trial_used:{chat_id}", "true")
        trial_end = datetime.now(timezone.utc) + timedelta(seconds=TRIAL_TTL)
        save_bot_status(chat_id, "stopped", custom_sub_end=trial_end)
        trial_text = translations['trial'][lang]
        async def send_trial():
            return await context.bot.send_message(chat_id=chat_id, text=trial_text)
        await retry_on_timeout(send_trial, chat_id=chat_id, message_text=trial_text)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    _, payload_chat_id, new_status = update.message.successful_payment.invoice_payload.split(":")
    
    if chat_id != int(payload_chat_id):
        return

    user_data = get_user_data(chat_id)
    lang = get_user_language(update, user_data)
    now = datetime.now(timezone.utc)
    current_end_ts = int(user_data.get("subscription_end", "0"))
    current_end = datetime.fromtimestamp(current_end_ts, tz=timezone.utc)

    if current_end > now:
        new_end = current_end + timedelta(days=30)
    else:
        new_end = now + timedelta(days=30)

    save_bot_status(chat_id, new_status, custom_sub_end=new_end)
    formatted_date = new_end.strftime("%d-%m-%Y %H:%M" if lang == "ru" else "%Y-%m-%d %H:%M")
    payment_text = translations['payment'][lang].format(date=formatted_date)
    await send_status_message(chat_id, context, payment_text, lang)

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async def send_pre_checkout():
        return await context.bot.answer_pre_checkout_query(update.pre_checkout_query.id, ok=True)
    await retry_on_timeout(send_pre_checkout, chat_id=update.pre_checkout_query.from_user.id, message_text="Pre-checkout confirmation")
