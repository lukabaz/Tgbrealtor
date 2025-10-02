import orjson
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from authorization.subscription import save_user_data, send_status_message
from utils.logger import setup_logger
from utils.telegram_utils import retry_on_timeout

# Настройка логгера
logger = setup_logger("webhook", "logs/bot.log")

def format_filters_response(filters):
    """Форматирование ответа с фильтрами"""
    city_map = {'1': 'Тбилиси', '2': 'Батуми', '3': 'Кутаиси'}
    deal_type_map = {'rent': 'Аренда', 'sale': 'Продажа'}
    own_ads_map = {'1': 'Да', '0': 'Нет'}

    city = city_map.get(filters.get('city', ''), 'Не указан')
    districts = []
    for city_key in ['tbilisi', 'batumi', 'kutaisi']:
        districts.extend(filters.get('districts', {}).get(city_key, []))
    response = (
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
    logger.info(f"Formatted filters response: {response}")
    return response

async def webhook_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка вебхука Telegram"""
    chat_id = update.message.chat_id
    logger.info(f"Received webhook update for chat_id: {chat_id}")

    try:
        filters_data = orjson.loads(update.message.web_app_data.data)
        logger.debug(f"Parsed webhook data: {filters_data}")

        if "url" in filters_data:
            logger.info(f"Saving filters for chat_id: {chat_id}")
            save_user_data(chat_id, {"filters_url": filters_data["url"]})
            utc_timestamp = int(datetime.now(timezone.utc).timestamp())
            logger.info(f"Saving filters_timestamp: {utc_timestamp} (UTC)")
            save_user_data(chat_id, {"filters_timestamp": str(utc_timestamp)})

            async def send_confirmation():
                logger.info(f"Sending confirmation to chat_id: {chat_id}")
                await send_status_message(chat_id, context, format_filters_response(filters_data))
            await retry_on_timeout(send_confirmation, chat_id=chat_id, message_text="Фильтры сохранены!")
            logger.info(f"Filters saved and confirmation sent to chat_id: {chat_id}")

        elif "supportMessage" in filters_data:
            message = filters_data["supportMessage"]
            logger.info(f"Received support message from chat_id: {chat_id}: {message}")
            await context.bot.send_message('6770986953', f"📩 Поддержка от {chat_id}:\n{message}")
            await context.bot.send_message(chat_id, "✅ Ваше сообщение отправлено в поддержку.")
            logger.info(f"Support message sent to admin and confirmation sent to chat_id: {chat_id}")

        else:
            logger.warning(f"No valid data in webhook for chat_id: {chat_id}")
            await send_status_message(chat_id, context, "Ошибка: URL не сформирован")

    except orjson.JSONDecodeError as e:
        logger.error(f"Failed to parse webhook data for chat_id: {chat_id}: {e}")
        await send_status_message(chat_id, context, "Ошибка: Неверный формат данных")
    except Exception as e:
        logger.error(f"Error processing webhook for chat_id: {chat_id}: {e}")
        await send_status_message(chat_id, context, "Ошибка при обработке данных")