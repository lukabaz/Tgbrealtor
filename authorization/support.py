from telegram.ext import ContextTypes
from telegram import Update
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