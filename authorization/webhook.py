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


def safe_int(value, default=0):
    try:
        return int(str(value).replace(" ", ""))
    except (ValueError, TypeError):
        return default


def build_myhome_url(settings: dict) -> str:
    city_map = {
        "1": {"id": "1", "slug": "Tbilisi"},
        "2": {"id": "15", "slug": "Batumi"},
        "3": {"id": "3", "slug": "Kutaisi"},
    }

    district_map = {
        "tbilisi": {
            "Vake-Saburtalo": {"district": "10"},
            "Didube-Chugureti": {"district": "11"},
            "Gldani-Nadzaladevi": {"district": "12"},
            "Isani-Samgori": {"district": "13"},
            "Tbilisi Suburb": {"district": "14"},
        },
        "batumi": {
            "Rustaveli": {"district": "8", "urban": "72"},
            "Bagrationi": {"district": "9", "urban": "73"},
            "Agmashenebeli": {"district": "10", "urban": "74"},
            "Javakhishvilli": {"district": "11", "urban": "75"},
            "Khimshiashvili": {"district": "13", "urban": "76"},
            "Airport": {"district": "15", "urban": "77"},
            "Old Batumi": {"district": "7", "urban": "71"},
            "Makhinjauri": {"district": "466"},
            "Tamar": {"district": "2999"},
            "Boni-Gorodok": {"district": "3009"},
            "Kakhabri": {"district": "2995"},
        },
        "kutaisi": {
            "Byols": {"district": "20"},
            "Avtokarkhana": {"district": "21"},
            "Nikea": {"district": "22"},
            "Hill": {"district": "23"},
            "Choma": {"district": "24"},
        },
    }

    city_id = settings.get("city")
    city_info = city_map.get(city_id)
    if not city_info:
        return ""

    city_key = city_info["slug"].lower()
    selected_districts = settings.get("districts", {}).get(city_key, [])

    districts = []
    urbans = []

    for name in selected_districts:
        mapping = district_map.get(city_key, {}).get(name)
        if mapping:
            if "district" in mapping:
                districts.append(mapping["district"])
            if "urban" in mapping:
                urbans.append(mapping["urban"])

    deal_type_map = {"sale": "1", "rent": "2"}
    deal_type = deal_type_map.get(settings.get("deal_type", ""), "1")

    price_from = safe_int(settings.get("price_from"))
    price_to = safe_int(settings.get("price_to"))
    floor_from = safe_int(settings.get("floor_from"))
    floor_to = safe_int(settings.get("floor_to"))
    rooms_from = safe_int(settings.get("rooms_from"))
    rooms_to = safe_int(settings.get("rooms_to"))
    bedrooms_from = safe_int(settings.get("bedrooms_from"))
    bedrooms_to = safe_int(settings.get("bedrooms_to"))

    rooms = ",".join(str(i) for i in range(rooms_from, rooms_to + 1)) if rooms_from and rooms_to else ""
    bedrooms = ",".join(str(i) for i in range(bedrooms_from, bedrooms_to + 1)) if bedrooms_from and bedrooms_to else ""
    own_ads = "physical" if str(settings.get("own_ads", "")).lower() == "true" else "all"

    base_path = {
        "1": "/s/iyideba-bina-Tbilisshi",
        "2": "/s/qiravdeba-bina-Batumshi",
        "3": "/s/iyideba-bina-Kutaisshi"
    }.get(city_id, "/s/iyideba-bina-Tbilisshi")

    base_url = f"https://www.myhome.ge/ru{base_path}"

    params = [
        "CardView=1",
        "real_estate_types=1",
        "with_picture=1",
        "currency_id=2",
        "order_by=date",
        "sequence=desc",
        f"cities={city_info['id']}",
        f"deal_types={deal_type}",
        f"price_from={price_from}",
        f"price_to={price_to}",
        f"floor_from={floor_from}",
        f"floor_to={floor_to}",
        f"owner_type={own_ads}",
        "page=1",
    ]
    if rooms:
        params.append(f"room_types={rooms}")
    if bedrooms:
        params.append(f"bedroom_types={bedrooms}")
    if districts:
        params.append(f"districts={','.join(districts)}")
    if urbans:
        params.append(f"urbans={','.join(urbans)}")

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
                async def send_error():
                    return await context.bot.send_message(chat_id=user_id, text=error_text)
                await retry_on_timeout(send_error)
                return

            forward_text = (
                f"📨 Новый вопрос от пользователя {update.effective_user.first_name or ''} "
                f"(@{update.effective_user.username or 'нет'})\n"
                f"ID пользователя: {user_id}\n\n{message}"
            )
            async def send_to_support():
                return await context.bot.send_message(SUPPORT_CHAT_ID, forward_text)
            await retry_on_timeout(send_to_support)

            response_text = translations['support_sent'][lang]
            async def send_confirmation():
                return await context.bot.send_message(chat_id=user_id, text=response_text)
            await retry_on_timeout(send_confirmation)

        elif data_type == "settings":
            settings = {
                "city": payload.get("city"),
                "districts": payload.get("districts", {}),
                "deal_type": payload.get("deal_type"),
                "price_from": payload.get("price_from"),
                "price_to": payload.get("price_to"),
                "floor_from": payload.get("floor_from"),
                "floor_to": payload.get("floor_to"),
                "rooms_from": payload.get("rooms_from"),
                "rooms_to": payload.get("rooms_to"),
                "bedrooms_from": payload.get("bedrooms_from"),
                "bedrooms_to": payload.get("bedrooms_to"),
                "own_ads": payload.get("own_ads", False),
            }

            url = build_myhome_url(settings)

            user_data = {
                "settings": url,
                "filters_timestamp": str(int(time.time())),
                "language": payload.get("language", "ru"),
            }

            save_user_data(user_id, user_data)
            redis_client.expire(f"user:{user_id}", INACTIVITY_TTL)

            if redis_client.hget(f"user:{user_id}", "bot_status") == "running":
                redis_client.sadd("subscribed_users", user_id)

            #await context.application.subscription_manager.refresh_subscriptions()

            city_map = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}
            deal_type_map = {"sale": "Продажа", "rent": "Аренда"}

            city = city_map.get(settings["city"], "Не выбран")
            deal_type = deal_type_map.get(settings["deal_type"], "Не указано")
            districts = settings.get("districts", {}).get(city.lower(), [])
            price = f'{settings["price_from"]}-{settings["price_to"]}$'
            floor = f'{settings["floor_from"]}-{settings["floor_to"]}'
            rooms = f'{settings["rooms_from"]}-{settings["rooms_to"]}'
            bedrooms = f'{settings["bedrooms_from"]}-{settings["bedrooms_to"]}'
            own_ads = "Да" if str(settings["own_ads"]).lower() == "true" else "Нет"

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

            async def send_confirmation():
                return await context.bot.send_message(chat_id=user_id, text=response_text)
            await retry_on_timeout(send_confirmation)

        else:
            error_text = translations['unknown_type'][lang]
            async def send_unknown():
                return await context.bot.send_message(chat_id=user_id, text=error_text)
            await retry_on_timeout(send_unknown)

    except Exception as e:
        logger.error(f"❌ Error processing Web App data for user_id={user_id}: {e}", exc_info=True)
        error_text = translations['processing_error'][lang]
        async def send_error():
            return await context.bot.send_message(chat_id=user_id, text=error_text)
        await retry_on_timeout(send_error)