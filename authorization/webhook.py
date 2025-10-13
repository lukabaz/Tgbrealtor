# authorization/webhook.py
import orjson
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import SUPPORT_CHAT_ID
from authorization.subscription import save_user_data, send_status_message
from utils.logger import logger
from utils.redis_client import redis_client
from utils.telegram_utils import retry_on_timeout
from utils.translations import translations

INACTIVITY_TTL = int(1.2 * 30 * 24 * 60 * 60)  # 1.2 месяца

def build_myhome_url(settings: dict) -> str:
    city_id = settings["city"]
    deal_type = settings["deal_type"]
    price_from = settings["price_from"]
    price_to = settings["price_to"]
    floor_from = settings["floor_from"]
    floor_to = settings["floor_to"]
    rooms = ",".join(str(i) for i in range(int(settings["rooms_from"]), int(settings["rooms_to"]) + 1))
    bedrooms = ",".join(str(i) for i in range(int(settings["bedrooms_from"]), int(settings["bedrooms_to"]) + 1))
    own_ads = "physical" if str(settings.get("own_ads", "")).lower() == "true" else "all"

    # District and urban mapping
    city_map = {
        "1": {"id": 1, "slug": "Tbilisi", "districts": {}, "urbans": []},
        "2": {"id": 15, "slug": "Batumi", "districts": {"Rustaveli": 8, "Agmashenebeli": 10, "Bagrationi": 9}, "urbans": [72, 74, 73]},
        "3": {"id": 2, "slug": "Kutaisi", "districts": {}, "urbans": []}
    }

    city_info = city_map.get(city_id)
    if not city_info:
        return ""

    # Convert selected district names to their IDs
    selected_districts = settings.get("districts", {}).get(city_info["slug"].lower(), [])
    district_ids = [str(city_info["districts"][d]) for d in selected_districts if d in city_info["districts"]]
    urbans = ",".join(str(u) for u in city_info["urbans"])

    base_url = f"https://www.myhome.ge/ru/s/qiravdeba-bina-{city_info['slug']}shi"
    params = [
        f"CardView=1",
        f"real_estate_types=1",
        f"with_picture=1",
        f"currency_id=2",
        f"order_by=date",
        f"sequence=desc",
        f"cities={city_info['id']}",
        f"deal_types={deal_type}",
        f"price_from={price_from}",
        f"price_to={price_to}",
        f"floor_from={floor_from}",
        f"floor_to={floor_to}",
        f"room_types={rooms}",
        f"bedroom_types={bedrooms}",
        f"owner_type={own_ads}",
        f"page=1"
    ]
    if district_ids:
        params.append(f"districts={','.join(district_ids)}")
    if urbans:
        params.append(f"urbans={urbans}")

    return f"{base_url}?{'&'.join(params)}"

async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.web_app_data:
        return

    user_id = update.effective_user.id
    try:
        payload = orjson.loads(update.message.web_app_data.data)
        logger.debug(f"📩 Received Web App data for user_id={user_id}: {payload}")

        user_data = redis_client.hgetall(f"user:{user_id}")
        lang = user_data.get("language", update.effective_user.language_code[:2])
        lang = lang if lang in ['ru', 'en'] else 'en'

        data_type = payload.get("type")
        
        if data_type == "support":
            message = (payload.get("message") or "").strip()
            if not message:
                error_text = translations['support_empty'][lang]
                await retry_on_timeout(context.bot.send_message, chat_id=user_id, text=error_text)
                return

            forward_text = (
                f"📨 Новый вопрос от пользователя {update.effective_user.first_name or ''} "
                f"(@{update.effective_user.username or 'нет'})\n"
                f"ID пользователя: {user_id}\n\n{message}"
            )
            await context.bot.send_message(SUPPORT_CHAT_ID, forward_text)
            response_text = translations['support_sent'][lang]
            await retry_on_timeout(context.bot.send_message, chat_id=user_id, text=response_text)

        elif data_type == "settings":
            required_keys = {"city", "deal_type", "price_from", "price_to", "floor_from", "floor_to", "rooms_from", "rooms_to", "bedrooms_from", "bedrooms_to", "own_ads"}
            if not required_keys.issubset(payload.keys()):
                error_text = translations['invalid_data'][lang]
                await retry_on_timeout(context.bot.send_message, chat_id=user_id, text=error_text)
                return

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

            url = build_myhome_url(settings)

            user_data = {
                "settings": url,
                "filters_timestamp": str(int(time.time())),
                "language": payload.get("language", "ru")
            }
            save_user_data(user_id, user_data)
            redis_client.expire(f"user:{user_id}", INACTIVITY_TTL)

            if redis_client.hget(f"user:{user_id}", "bot_status") == "running":
                redis_client.sadd("subscribed_users", user_id)

            await context.application.subscription_manager.refresh_subscriptions()

            # Формируем текст для отправки
            city_map = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}
            deal_type_map = {"1": "Продажа", "2": "Аренда"}

            city = city_map.get(settings["city"], "Не выбран")
            deal_type = deal_type_map.get(settings["deal_type"], "Не указано")
            districts = settings.get("districts", {}).get(city.lower(), [])
            price = f'{settings["price_from"]}-{settings["price_to"]}$'
            floor = f'{settings["floor_from"]}-{settings["floor_to"]}'
            rooms = f'{settings["rooms_from"]}-{settings["rooms_to"]}'
            bedrooms = f'{settings["bedrooms_from"]}-{settings["bedrooms_to"]}'
            own_ads = "Да" if settings["own_ads"] == "1" else "Нет"

            response_text = (
                "✅ Фильтры сохранены!\n"
                f"Город: {city}\n"
                f"Районы: {', '.join(districts) if districts else 'Не выбраны'}\n"
                f"Тип сделки: {deal_type}\n"
                f"Цена: {price}\n"
                f"Этаж: {floor}\n"
                f"Комнат: {rooms}\n"
                f"Спален: {bedrooms}\n"
                f"Только собственник: {own_ads}"
            )

            await retry_on_timeout(context.bot.send_message, chat_id=user_id, text=response_text)

        else:
            error_text = translations['unknown_type'][lang]
            await retry_on_timeout(context.bot.send_message, chat_id=user_id, text=error_text)

    except Exception as e:
        logger.error(f"❌ Error processing Web App data for user_id={user_id}: {e}", exc_info=True)
        error_text = translations['processing_error'][lang]
        await retry_on_timeout(send_status_message, user_id, context, error_text)