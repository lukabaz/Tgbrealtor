# api/webhook
import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler, CommandHandler
import orjson  # Для JSON parse (как в webhook.py)
from datetime import datetime, timezone
from authorization.subscription import save_user_data, welcome_new_user, handle_buttons, successful_payment, pre_checkout  # Импорт handlers из subscription (без handle_user_message)
from authorization.webhook import webhook_update  # , format_filters_response Импорт webhook_update и format
from authorization.support import handle_support_text  # Отдельный импорт для handle_user_message
from utils.logger import logger
from utils.telegram_utils import retry_on_timeout
from config import TELEGRAM_TOKEN
from config import SUPPORT_CHAT_ID

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

# Global Application (lazy init в эндпоинтах для serverless cold starts)
application = None

async def init_application():
    """Async helper: инициализирует Application, добавляет handlers и логирует."""
    global application
    if application is not None:  # Избегаем повторной init
        return
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    await application.initialize()  # Обязательно для v21+: инициализирует bot и internals
    # Add handlers from bot.py (как в startup, но здесь)
    application.add_handler(MessageHandler(
        filters.Chat(SUPPORT_CHAT_ID) & filters.TEXT & ~filters.COMMAND,
        handle_support_text
    ))

    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    logger.info("Bot application initialized on cold start")

@app.post("/webhook")  # POST от Netlify (web_app_data)
async def netlify_webhook(request: Request):
    global application
    if application is None:
        await init_application()  # Lazy init перед использованием bot
    try:
        body = await request.body()
        data = orjson.loads(body)  # Как в webhook.py
        chat_id = data.get('chat_id')  # From Netlify payload
        if 'url' in data:
            save_user_data(chat_id, {"filters_url": data["url"]})
            utc_timestamp = int(datetime.now(timezone.utc).timestamp())
            logger.info("💾 Saving filters_timestamp as: %s (UTC)", utc_timestamp)
            save_user_data(chat_id, {"filters_timestamp": str(utc_timestamp)})
            # Send confirmation (from webhook.py)
            #message = format_filters_response(data) убрал потому что from authorization.webhook import webhook_update  # , format_filters_response 
            async def send_confirmation():
                await application.bot.send_message(chat_id=chat_id, text=message)
            await retry_on_timeout(send_confirmation, chat_id=chat_id, message_text="Фильтры сохранены!")
            return {"status": "filters saved"}
        elif 'supportMessage' in data:
            message = data["supportMessage"]
            async def send_support():
                await application.bot.send_message('6770986953', f"📩 Поддержка от {chat_id}:\n{message}")
                await application.bot.send_message(chat_id, "✅ Ваше сообщение отправлено в поддержку.")
            await retry_on_timeout(send_support, chat_id=chat_id, message_text="Support sent!")
            return {"status": "support sent"}
        else:
            return {"status": "ok", "error": "No url or supportMessage"}
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    global application

    # Проверка: если event loop закрыт — пересоздаём
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("Event loop is closed")
    except RuntimeError:
        # Создаём новый loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        application = None  # 💥 ВАЖНО: Заставим пересоздать application в новом loop-е

    # Lazy init (или повторная инициализация после краша loop-а)
    if application is None:
        await init_application()

    try:
        body = await request.body()
        update_json = orjson.loads(body)
        update = Update.de_json(update_json, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.exception(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))
    