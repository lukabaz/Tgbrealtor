# authorization/support.py
from python_telegram_bot import Update  # Исправлено: из библиотеки
from python_telegram_bot.ext import ContextTypes  # Исправлено: из библиотеки
import re
from utils.logger import logger

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
                await update.message.reply_text("❌ Пожалуйста, введите непустой текст ответа.")
                return

            logger.debug(f"📤 Sending reply to user {user_id}: {reply}")

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"💬 Ответ поддержки:\n{reply}",
                    disable_web_page_preview=True
                )
                await update.message.reply_text("✅ Ответ отправлен пользователю.")
                logger.info(f"✅ Ответ отправлен пользователю {user_id}: {reply}")
            except Exception as e:
                logger.exception(f"❌ Ошибка при отправке ответа пользователю {user_id}: {e}")
                error_message = f"❌ Не удалось отправить сообщение пользователю: {str(e)}"
                await update.message.reply_text(error_message)
        else:
            logger.debug("ℹ️ Not a reply to a support message, ignoring")
    else:
        logger.debug("ℹ️ No reply context, ignoring message")
        
known_buttons = {"🔴 Старт","🟢 Стоп","🎁 Бесплатно","⚙️ Настройки","💬 Поддержка"}
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    message_text = update.message.text

    if message_text in known_buttons:
        return

    await context.bot.send_message(chat_id, "❗Для обращения нажмите на панели меню кнопку Поддержка.")

async def reply_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    response = "Мы получили ваш запрос и работаем над решением. Спасибо за терпение."
    await context.bot.send_message(chat_id, response)