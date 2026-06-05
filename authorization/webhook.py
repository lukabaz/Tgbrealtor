# authorization/webhook.py
import orjson
import time
from telegram import Update
from telegram.ext import ContextTypes
from config import SUPPORT_CHAT_ID
from authorization.subscription import save_user_data
from utils.logger import logger
from utils.redis_client import redis_client
from utils.telegram_utils import retry_on_timeout
from utils.translations import translations

from pymongo import MongoClient
from datetime import datetime
from config import MONGO_URI

mongo = MongoClient(MONGO_URI)
db = mongo["real_estate"]
agents_collection = db["agents"]


INACTIVITY_TTL = int(1.2 * 30 * 24 * 60 * 60)  # 1.2 месяца

def safe_int(value, default=0):
    try:
        return int(str(value).replace(" ", ""))
    except (ValueError, TypeError):
        return default

def build_myhome_url(settings: dict) -> str:
    city_map = {
        "1": {"id": "1", "slug": "tbilisi"},
        "2": {"id": "15", "slug": "batumi"},
        "3": {"id": "96", "slug": "kutaisi"},
    }

    district_map = {
        "tbilisi": {
            "Vake-Saburtalo": {"district": "4",  "urban": "38,39,40,41,42,43,44,45,46,47,101,28,30,48,106,111,121,29", "slug": "vake"},
            "Didube-Chugureti": {"district": "3", "urban": "23,24,25,27,103,26", "slug": "didube"},
            "Gldani-Nadzaladevi": {"district": "1", "urban": "2,3,4,5,6,7,8,9,10,11,12,120,1,122", "slug": "gldani"},
            "Isani-Samgori":      {"district": "5", "urban": "49,50,51,52,53,54,55,56,58,59,60,78,117", "slug": "varketili"},
            "Tbilisi Suburb":     {"district": "2", "urban": "68,13,14,15,16,17,18,19,20,21,22,69,70,102,118", "slug": "wveri"},
        },
        "batumi": {
            "Rustaveli": {"district": "8", "slug": "rustavelis-ubani"},
            "Bagrationi":     {"district": "9",   "slug": "bagrationis-ubani"},
            "Agmashenebeli":  {"district": "10",  "slug": "aghmasheneblis-ubani"},
            "Javakhishvilli": {"district": "11",  "slug": "javakhishvilis-ubani"},
            "Khimshiashvili": {"district": "13",  "slug": "khimshiashvilis-ubani"},
            "Airport":        {"district": "15",  "slug": "aeroportis-ubani"},
            "Old Batumi":     {"district": "7",   "slug": "dzveli-batumis-ubani"},     
            "Makhinjauri":    {"district": "466", "slug": "makhinjauri"},
            "Tamar":          {"district": "2999","slug": "tamaris-dasakhleba"},       
            "Boni-Gorodok":   {"district": "3009","slug": "boni-gorodokis-ubani"},
            "Kakhabri":       {"district": "2995","slug": "kakhabris-ubani"},
        },
        "kutaisi": { 
            "Avtokarkhana": {"district": "25", "slug": "avtoqarkhana"},    # обновлено "Byols":        {"district": "20", "slug": "byols"}, "Hill":         {"district": "23", "slug": "????"},            # если нужно добавить
            "Nikea":        {"district": "29", "slug": "nikea"},          
            "Choma":        {"district": "31", "slug": "tchoma"},
            "Ninoshvili":   {"district": "42", "slug": "ninoshvili"},
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
    district_slugs = []   

    for name in selected_districts:
        mapping = district_map.get(city_key, {}).get(name)
        if mapping:
            districts.append(mapping.get("district"))
            if "urban" in mapping:
                urbans.append(mapping["urban"])
            if "slug" in mapping:                                 # ← новое
                district_slugs.append(mapping["slug"])    

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

    # ==================== НОВЫЙ УНИВЕРСАЛЬНЫЙ ФОРМАТ ====================
    deal_slug = "prodazha" if deal_type == "1" else "arenda"
    base_path = f"/ru/nedvizhimost/{deal_slug}/kvartira/{city_info['slug']}"

    district_part = f"/{district_slugs[0]}" if district_slugs else ""
    base_url = f"https://www.myhome.ge{base_path}{district_part}/"

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

    # Slug-параметры (важны для новой структуры)
    params.extend([
        f"slug=nedvizhimost",
        f"slug={deal_slug}",
        "slug=kvartira",
        f"slug={city_info['slug']}",
    ])
    if district_slugs:
        params.append(f"slug={district_slugs[0]}")

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

            # Логирование содержимого settings["districts"]
            logger.debug(f"Settings districts: {settings['districts']}")

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

            city_map = {"1": "Тбилиси", "2": "Батуми", "3": "Кутаиси"}
            city_key_map = {"1": "tbilisi", "2": "batumi", "3": "kutaisi"}
            deal_type_map = {"sale": "Продажа", "rent": "Аренда"}

            city = city_map.get(settings["city"], "Не выбран")
            city_key = city_key_map.get(settings["city"], "tbilisi")
            deal_type = deal_type_map.get(settings["deal_type"], "Не указано")
            districts = settings.get("districts", {}).get(city_key, [])
            own_ads = "Да" if str(settings["own_ads"]).lower() == "true" else "Нет"

            # === Сохранение фильтра агента в MongoDB ===
            agent_doc = {
                "chat_id": user_id,
                "language": lang,
                "active": False,  # ❗️по умолчанию выключен, активируется позже при запуске
                "updated_at": datetime.utcnow(),
                "filters": {
                    "city": city_map.get(settings["city"], "Unknown"),
                    "deal_type": settings.get("deal_type"),
                    "price_from": safe_int(settings.get("price_from")),
                    "price_to": safe_int(settings.get("price_to")),
                    "floor_from": safe_int(settings.get("floor_from")),      
                    "floor_to": safe_int(settings.get("floor_to")), 
                    "rooms_from": safe_int(settings.get("rooms_from")),
                    "rooms_to": safe_int(settings.get("rooms_to")),
                    "bedrooms_from": safe_int(settings.get("bedrooms_from")),  
                    "bedrooms_to": safe_int(settings.get("bedrooms_to")),  
                    "districts": settings.get("districts", {}).get(city_key, []),
                    "own_ads": str(settings.get("own_ads")).lower() == "true"
                }
            }

            agents_collection.update_one(
                {"chat_id": user_id},
                {"$set": agent_doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
                upsert=True
            )

            def format_range(start, end, suffix="", lang="ru"):
                try:
                    start = int(start)
                except (ValueError, TypeError):
                    start = None
                try:
                    end = int(end)
                except (ValueError, TypeError):
                    end = None

                if lang == "en":
                    if start is None and end is None:
                        return "Not specified"
                    elif start is None:
                        return f"Up to {end}{suffix}"
                    elif end is None:
                        return f"From {start}{suffix}"
                    else:
                        return f"{start}-{end}{suffix}"
                else:  # default to Russian
                    if start is None and end is None:
                       return "Не указано"
                    elif start is None:
                        return f"До {end}{suffix}"
                    elif end is None:
                        return f"От {start}{suffix}"
                    else:
                        return f"{start}-{end}{suffix}"

            price = format_range(settings["price_from"], settings["price_to"], suffix="$", lang=lang)
            floor = format_range(settings["floor_from"], settings["floor_to"], lang=lang)
            rooms = format_range(settings["rooms_from"], settings["rooms_to"], lang=lang)
            bedrooms = format_range(settings["bedrooms_from"], settings["bedrooms_to"], lang=lang)

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