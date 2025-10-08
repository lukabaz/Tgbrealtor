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

def format_settings_response(data: dict, language: str = "ru") -> str:
    """Форматирует ответ с настройками фильтров недвижимости для пользователя."""
    # Маппинг значений
    city_map = {
        "1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"
    }
    deal_type_map = {
        "rent": "Аренда", "sale": "Продажа"
    }

    city = city_map.get(data.get("city"), "Не выбран")
    deal_type = deal_type_map.get(data.get("deal_type"), "Не указан")
    price_from = data.get("price_from") or "Не указано"
    price_to = data.get("price_to") or "Не указано"
    floor_from = data.get("floor_from") or "Не указано"
    floor_to = data.get("floor_to") or "Не указано"
    rooms_from = data.get("rooms_from") or "Не указано"
    rooms_to = data.get("rooms_to") or "Не указано"
    bedrooms_from = data.get("bedrooms_from") or "Не указано"
    bedrooms_to = data.get("bedrooms_to") or "Не указано"
    own_ads = "Да" if data.get("own_ads") == "1" else "Нет"
    url = data.get("url", "URL не найден")

    if language == "en":
        city_map_en = {"1": "Tbilisi", "2": "Batumi", "3": "Kutaisi"}
        deal_type_map_en = {"rent": "Rent", "sale": "Sale"}
        return (
            f"✅ Filters saved!\n"
            f"City: {city_map_en.get(data.get('city'), 'Not selected')}\n"
            f"Deal type: {deal_type_map_en.get(data.get('deal_type'), 'Not set')}\n"
            f"Price: ${price_from} - ${price_to}\n"
            f"Floor: {floor_from} - {floor_to}\n"
            f"Rooms: {rooms_from} - {rooms_to}\n"
            f"Bedrooms: {bedrooms_from} - {bedrooms_to}\n"
            f"Only from owners: {'Yes' if own_ads == 'Да' else 'No'}\n"
            f"🔗 [View on MyHome]({url})"
        )

    return (
        f"✅ Фильтры сохранены!\n"
        f"Город: {city}\n"
        f"Тип сделки: {deal_type}\n"
        f"Цена: {price_from}$ - {price_to}$\n"
        f"Этаж: {floor_from} - {floor_to}\n"
        f"Комнат: {rooms_from} - {rooms_to}\n"
        f"Спален: {bedrooms_from} - {bedrooms_to}\n"
        f"Только от владельцев: {own_ads}\n"
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
            logger.info(f"Payload city: {payload.get('city')}")

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
            city_map = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}
            deal_type_map = {"1": "Продажа", "2": "Аренда"}

            city = city_map.get(settings.get("city"), "Не выбран" if lang == "ru" else "Not selected")
            deal_type = deal_type_map.get(settings.get("deal_type"), "Не указан" if lang == "ru" else "Not set")


            response_text = translations['settings_saved'][lang].format(
            city=city,    
            districts=', '.join(settings.get("districts", {}).values()) or ("Не выбраны" if lang == "ru" else "Not selected"),
            deal_type=deal_type,
            price_from=settings.get("price_from") or ("Не указано" if lang == "ru" else "Not specified"),
            price_to=settings.get("price_to") or ("Не указано" if lang == "ru" else "Not specified"),
            floor_from=settings.get("floor_from") or ("Не указано" if lang == "ru" else "Not specified"),
            floor_to=settings.get("floor_to") or ("Не указано" if lang == "ru" else "Not specified"),
            rooms_from=settings.get("rooms_from") or ("Не указано" if lang == "ru" else "Not specified"),
            rooms_to=settings.get("rooms_to") or ("Не указано" if lang == "ru" else "Not specified"),
            bedrooms_from=settings.get("bedrooms_from") or ("Не указано" if lang == "ru" else "Not specified"),
            bedrooms_to=settings.get("bedrooms_to") or ("Не указано" if lang == "ru" else "Not specified"),
            own_ads="Да" if settings.get("own_ads") == "1" and lang == "ru" else "Yes" if settings.get("own_ads") == "1" else ("Нет" if lang == "ru" else "No")
            )
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
