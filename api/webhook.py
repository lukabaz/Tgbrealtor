# api/webhook
import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, CommandHandler, ChatMemberHandler
import orjson  # Для JSON parse (как в webhook.py)
from authorization.subscription import start_command, welcome_new_user, handle_buttons, successful_payment, pre_checkout  # Импорт handlers из subscription (без handle_user_message)
from authorization.webhook import webhook_update  # , format_filters_response Импорт webhook_update и format
from authorization.support import handle_support_text # Отдельный импорт для handle_user_message
from utils.logger import logger
from config import TELEGRAM_TOKEN, SUPPORT_CHAT_ID
from utils.redis_client import redis_client # Импорт redis_client для работы с черным списком

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# Global Application (lazy init в эндпоинтах для serverless cold starts)
#application = None

async def build_application():
    """Создает Telegram Application с нужными хендлерами."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    await application.initialize()

    application.add_handler(MessageHandler(
        filters.Chat(SUPPORT_CHAT_ID) & filters.TEXT & ~filters.COMMAND,
        handle_support_text
    ))
   
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    return application

@app.get("/api/blacklist/{user_id}")
async def get_blacklist(user_id: int):
    phones = list(redis_client.smembers(f"blacklist:{user_id}"))
    return {"phones": sorted(phones)}

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    try:
        body = await request.body()
        update_json = orjson.loads(body)

        application = await build_application()
        update = Update.de_json(update_json, application.bot)

        await application.process_update(update)

        async def shutdown_later(app, delay: float = 0.0):
            if delay > 0:
                await asyncio.sleep(delay)
            await app.shutdown()
        # Определяем нового пользователя безопасно
        is_new_user = getattr(update, "my_chat_member", None) and update.my_chat_member.new_chat_member.status in ["member", "administrator"]
        # Управляемый delay для serverless
        asyncio.create_task(shutdown_later(application, delay=1.5 if is_new_user else 1.5))

    
    except Exception as e:
        logger.exception(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))