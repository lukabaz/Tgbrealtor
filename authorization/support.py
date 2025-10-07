# authorization/support.py
from telegram import Update
from telegram.ext import ContextTypes
import re
from utils.logger import logger
from utils.translations import translations
from authorization.subscription import get_user_data, get_user_language

async def handle_support_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug("📥 handle_support_text triggered")
    logger.debug(f"👤 From user: {update.effective_user.id}, chat: {update.effective_chat.id}")

    # Check if this is a reply to a support message
    if update.message.reply_to_message:
        original_message = update.message.reply_to_message.text
        user_id_match = re.search(r"ID пользователя: (\d+)", original_message)
        if user_id_match:
            user_id = int(user_id_match.group(1))
            reply = update.message.text or ""
            if not reply.strip():
                logger.warning("⚠️ Empty reply message, ignoring")
                user_data = get_user_data(update.effective_chat.id)
                lang = get_user_language(update, user_data)
                error_text = translations['support_empty_reply'][lang]
                await update.message.reply_text(error_text)
                return

            logger.debug(f"📤 Sending reply to user {user_id}: {reply}")

            try:
                # Получаем язык получателя (user_id)
                user_data = get_user_data(user_id)
                lang = get_user_language(update, user_data)
                reply_text = translations['support_reply'][lang].format(reply=reply)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=reply_text,
                    disable_web_page_preview=True
                )
                # Получаем язык отправителя (администратора)
                admin_data = get_user_data(update.effective_chat.id)
                admin_lang = get_user_language(update, admin_data)
                success_text = translations['support_reply_sent'][admin_lang]
                await update.message.reply_text(success_text)
                logger.info(f"✅ Ответ отправлен пользователю {user_id}: {reply}")
            except Exception as e:
                logger.exception(f"❌ Ошибка при отправке ответа пользователю {user_id}: {e}")
                admin_data = get_user_data(update.effective_chat.id)
                admin_lang = get_user_language(update, admin_data)
                error_text = translations['support_reply_error'][admin_lang].format(error=str(e))
                await update.message.reply_text(error_text)
        else:
            logger.debug("ℹ️ Not a reply to a support message, ignoring")
    else:
        logger.debug("ℹ️ No reply context, ignoring message")

# Кнопки основного меню, чтобы не реагировать на них как на произвольный текст
#known_buttons = {"🔴 Старт", "🟢 Стоп", "🎁 Бесплатно", "⚙️ Настройки", "💬 Поддержка"}
# 1. Сообщение пользователя, пришедшее обычным текстом, а не через WebApp
#async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    #text = update.message.text
    #if text in known_buttons:
        #return
    #await context.bot.send_message(
        #update.effective_chat.id,
        #"❗Для обращения нажмите на панели меню кнопку «Поддержка».",
    #)  
