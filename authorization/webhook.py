# authorization/webhook.py
import orjson
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import SUPPORT_CHAT_ID
from authorization.subscription import save_user_data, send_status_message # get_user_data, get_user_language возможно нужен
from utils.logger import logger
from utils.redis_client import redis_client
from utils.telegram_utils import retry_on_timeout
from utils.translations import translations


INACTIVITY_TTL = int(1.2 * 30 * 24 * 60 * 60)  # 1.2 месяца


def format_filters_response(filters, lang="ru"):
    """Форматирует ответ с настройками для пользователя."""
    city_map = {'1': 'Тбилиси', '2': 'Батуми', '3': 'Кутаиси'}
    deal_type_map = {'rent': 'Аренда', 'sale': 'Продажа'}
    own_ads_map = {'1': 'Да', '0': 'Нет'}

    city = city_map.get(filters.get('city', ''), 'Не указан')
    districts = []
    for city_key in ['tbilisi', 'batumi', 'kutaisi']:
        districts.extend(filters.get('districts', {}).get(city_key, []))
    districts_str = ', '.join(districts) if districts else 'Не указаны' if lang == "ru" else 'Not specified'
    deal_type = deal_type_map.get(filters.get('deal_type', ''), 'Не указан' if lang == "ru" else 'Not specified')
    own_ads = own_ads_map.get(filters.get('own_ads', '0'), 'Не указан' if lang == "ru" else 'Not specified')

    return translations['settings_saved'][lang].format(
        city=city,
        districts=districts_str,
        deal_type=deal_type,
        price_from=filters.get('price_from', '0'),
        price_to=filters.get('price_to', '0'),
        floor_from=filters.get('floor_from', '0'),
        floor_to=filters.get('floor_to', '0'),
        rooms_from=filters.get('rooms_from', '0'),
        rooms_to=filters.get('rooms_to', '0'),
        bedrooms_from=filters.get('bedrooms_from', '0'),
        bedrooms_to=filters.get('bedrooms_to', '0'),
        own_ads=own_ads
    )

async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.web_app_data:
        return  # Not a WebApp message

    user_id = update.effective_user.id
    try:
        payload = orjson.loads(update.message.web_app_data.data)
        logger.debug(f"📩 Received Web App data for user_id={user_id}: {payload}")

        # Получаем язык пользователя
        user_data = redis_client.hgetall(f"user:{user_id}")
        lang = user_data.get("language", update.effective_user.language_code[:2])
        lang = lang if lang in ['ru', 'en'] else 'en'
        logger.info(f"Selected language for user_id={user_id}: {lang}")

        # Dispatch based on type
        data_type = payload.get("type")
        
        if data_type == "support":
            # Handle support message
            message = (payload.get("message") or "").strip()
            if not message:
                error_text = translations['support_empty'][lang]
                async def send_error():
                    return await context.bot.send_message(chat_id=user_id, text=error_text)
                await retry_on_timeout(send_error, chat_id=user_id, message_text=error_text)
                return

            try:
                # Forward to support chat with user ID
                forward_text = (
                    f"📨 Новый вопрос от пользователя {update.effective_user.first_name or ''} "
                    f"(@{update.effective_user.username or 'нет'})\n"
                    f"ID пользователя: {user_id}\n\n"
                    f"{message}"
                )
                await context.bot.send_message(SUPPORT_CHAT_ID, forward_text)

                # Confirm to user
                response_text = translations['support_sent'][lang]
                async def send_confirmation():
                    return await context.bot.send_message(chat_id=user_id, text=response_text)
                await retry_on_timeout(send_confirmation, chat_id=user_id, message_text=response_text)
            except Exception as e:
                logger.exception(f"Ошибка при пересылке сообщения поддержки для user_id={user_id}")
                error_text = translations['processing_error'][lang]
                async def send_error():
                    return await context.bot.send_message(chat_id=user_id, text=error_text)
                await retry_on_timeout(send_error, chat_id=user_id, message_text=error_text)
        
        elif data_type == "settings":
            # Handle settings update (original logic)
            logger.info(f"Payload stock_exchange: {payload.get('stock_exchange')}")

            # Проверяем наличие необходимых полей
            required_keys = {"city", "deal_type", "price_from", "price_to", "floor_from", "floor_to", "rooms_from", "rooms_to", "bedrooms_from", "bedrooms_to", "own_ads"}
            if not required_keys.issubset(payload.keys()):
                logger.warning(f"Invalid Web App data format for user_id={user_id}: {payload}")
                error_text = translations['invalid_data'][lang]
                async def send_error():
                    return await context.bot.send_message(chat_id=user_id, text=error_text)
                await retry_on_timeout(send_error, chat_id=user_id, message_text=error_text)
                return

            # Формируем настройки
            settings = {
                "city": payload["city"],
                "districts": payload.get("districts", {}),
                "deal_type": payload["deal_type"],
                "price_from": str(payload["price_from"]),
                "price_to": str(payload["price_to"]),
                "floor_from": str(payload["floor_from"]),
                "floor_to": str(payload["floor_to"]),
                "rooms_from": str(payload["rooms_from"]),
                "rooms_to": str(payload["rooms_to"]),
                "bedrooms_from": str(payload["bedrooms_from"]),
                "bedrooms_to": str(payload["bedrooms_to"]),
                "own_ads": str(payload["own_ads"])
            }
            # Сохраняем настройки и язык в user:<user_id>
            user_data = {
                "settings": orjson.dumps(settings),
                "filters_timestamp": str(int(time.time())),
                "language": payload.get("language", "ru")  # Save language from payload
            }
            save_user_data(user_id, user_data)

            redis_client.expire(f"user:{user_id}", INACTIVITY_TTL)  # Ensure TTL is set
            user_data = redis_client.hgetall(f"user:{user_id}")
            if user_data.get("bot_status", "stopped") == "running":
                redis_client.sadd("subscribed_users", user_id)
                logger.info(f"✅ Added user_id={user_id} to subscribed_users")
            logger.info(f"✅ Saved settings for user_id={user_id}: {settings}")
            logger.info(f"📋 Current subscribed_users: {redis_client.smembers('subscribed_users')}")
            
            # Проверяем подписку и статус бота
            subscription_end = user_data.get("subscription_end", "0")
            bot_status = user_data.get("bot_status", "stopped")
            logger.info(f"Webhook update for user_id={user_id}: subscription_end={subscription_end}, bot_status={bot_status}")

            # Force cache refresh
            await context.application.subscription_manager.refresh_subscriptions()

            # Формируем ответ
            response_text = format_filters_response(settings, lang)
            async def send_confirmation():
                return await context.bot.send_message(chat_id=user_id, text=response_text)
            await retry_on_timeout(send_confirmation, chat_id=user_id, message_text=response_text)

        else:
            logger.warning(f"Unknown type in WebApp data for user_id={user_id}: {data_type}")
            error_text = translations['unknown_type'][lang]
            async def send_error():
                return await context.bot.send_message(chat_id=user_id, text=error_text)
            await retry_on_timeout(send_error, chat_id=user_id, message_text=error_text)

    except Exception as e:
        logger.error(f"❌ Error processing Web App data for user_id={user_id}: {e}", exc_info=True)
        error_text = translations['processing_error'][lang]
        async def send_error():
            return await send_status_message(user_id, context, error_text)
        await retry_on_timeout(send_error, chat_id=user_id, message_text=error_text)
