# authorization/webhook.py
import orjson
from datetime import datetime, timezone
from python_telegram_bot import Update  # Исправлено: из библиотеки
from python_telegram_bot.ext import ContextTypes  # Исправлено: из библиотеки
from authorization.subscription import save_user_data, send_status_message
from utils.logger import logger
from utils.telegram_utils import retry_on_timeout

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
    filters_data = orjson.loads(update.message.web_app_data.data)

    if "url" in filters_data:
        save_user_data(chat_id, {"filters_url": filters_data["url"]})
        utc_timestamp = int(datetime.now(timezone.utc).timestamp())
        logger.info("💾 Saving filters_timestamp as: %s (UTC)", utc_timestamp)
        save_user_data(chat_id, {"filters_timestamp": str(utc_timestamp)})
        async def send_confirmation():
            await send_status_message(chat_id, context, format_filters_response(filters_data))
        await retry_on_timeout(send_confirmation, chat_id=chat_id, message_text="Фильтры сохранены!")
    elif "supportMessage" in filters_data:
        message = filters_data["supportMessage"]
        await context.bot.send_message('6770986953', f"📩 Поддержка от {chat_id}:\n{message}")
        await context.bot.send_message(chat_id, "✅ Ваше сообщение отправлено в поддержку.")    
    else:
        await send_status_message(chat_id, context, "Ошибка: URL не сформирован")