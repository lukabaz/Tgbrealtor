import os
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler
import orjson  # Для JSON parse (как в webhook.py)
import asyncio
from datetime import datetime, timezone
from authorization.subscription import save_user_data, send_status_message, welcome_new_user, handle_buttons, successful_payment, pre_checkout, handle_user_message  # Импорт handlers
from authorization.webhook import webhook_update, format_filters_response  # Импорт webhook_update и format
from utils.logger import logger
from utils.telegram_utils import retry_on_timeout
from config import TELEGRAM_TOKEN

app = FastAPI()

# Global Application (init on startup for cold start)
application = None

@app.on_event("startup")
async def startup_event():
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    # Add handlers from bot.py
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))
    logger.info("Bot application started on Vercel")

@app.post("/webhook")  # POST от Netlify (web_app_data)
async def netlify_webhook(request: Request):
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
            message = format_filters_response(data)
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

@app.post(f"/{TELEGRAM_TOKEN}")  # POST от Telegram (updates).
async def telegram_webhook(request: Request):
    try:
        body = await request.body()
        update_json = orjson.loads(body)
        update = Update.de_json(update_json, application.bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))