# api/webhook
import os
import asyncio
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler, CallbackQueryHandler, ContextTypes
import orjson  # Для JSON parse (как в webhook.py)
from authorization.subscription import save_user_data, welcome_new_user, handle_buttons, successful_payment, pre_checkout  # Импорт handlers из subscription (без handle_user_message)
from authorization.webhook import webhook_update  # , format_filters_response Импорт webhook_update и format
from authorization.support import handle_support_text  # Отдельный импорт для handle_user_message
from utils.logger import logger
from config import TELEGRAM_TOKEN
from config import SUPPORT_CHAT_ID

app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)
# Функция удаления сообщения
async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # обязательный отклик Telegram

    data = query.data

    if data.startswith("remove_"):
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat.id,
                message_id=query.message.message_id
            )
        except Exception as e:
            print("Ошибка удаления:", e)
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
    application.add_handler(CallbackQueryHandler(handle_remove))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
    application.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    return application

@app.post("/telegram-webhook")
async def telegram_webhook(request: Request):
    try:
        body = await request.body()
        update_json = orjson.loads(body)

        application = await build_application()
        update = Update.de_json(update_json, application.bot)

        # Определяем, нужно ли ждать (новый пользователь в чатах)
        is_new_user = False
        if update.my_chat_member:
            status = update.my_chat_member.new_chat_member.status
            # Если пользователь только присоединился или активировал бота
            if status in ["member", "administrator"]:
                is_new_user = True

        await application.process_update(update)

        async def shutdown_later(app, delay: float = 0.0):
            if delay > 0:
                await asyncio.sleep(delay)
            await app.shutdown()

        # Только для новых пользователей даем задержку
        if is_new_user:
            asyncio.create_task(shutdown_later(application, delay=1.5))
        else:
            asyncio.create_task(shutdown_later(application))

        return {"ok": True}
    
    except Exception as e:
        logger.exception(f"Telegram webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 3000)))