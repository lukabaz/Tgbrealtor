translations = {
    # Сообщения из subscription.py
    "welcome": {
        "ru": "Добро пожаловать! Настройте фильтры и нажмите 🔴 Старт",
        "en": "Welcome! Set up filters and press 🔴 Start"
    },
    "start": {
        "ru": "🔍 Мониторинг активирован! Ждём свежих объявлений.",
        "en": "🔍 Monitoring activated! Waiting for new announcements."
    },
    "stop": {
        "ru": "Мониторинг приостановлен 🛑.",
        "en": "Monitoring paused 🛑."
    },
    "stop_expired": {
        "ru": "Подписка истекла 🔴",
        "en": "Subscription expired 🔴"
    },
    "trial": {
        "ru": "Вам предоставлены 2 дня бесплатного доступа! Подписка активирована 🟢",
        "en": "You have been granted 2 days of free access! Subscription activated 🟢"
    },
    "trial_used": {
        "ru": "Вы уже использовали бесплатные 2 дня!",
        "en": "You have already used the 2-day free trial!"
    },
    "trial_active": {
        "ru": "У вас уже есть активная подписка! Бесплатный период можно активировать только после её окончания.",
        "en": "You already have an active subscription! The free trial can only be activated after it expires."
    },
    "invoice": {
        "ru": "Для активации мониторинга оформите подписку.",
        "en": "To activate monitoring, purchase a subscription."
    },
    "payment": {
        "ru": "Подписка продлена! 🟢\nНовая дата окончания: {date}",
        "en": "Subscription extended! 🟢\nNew expiration date: {date}"
    },
    "settings_button": {
        "ru": "⚙️ Настройки",
        "en": "⚙️ Settings"
    },
    "start_button": {
        "ru": "🔴 Старт",
        "en": "🔴 Start"
    },
    "stop_button": {
        "ru": "🟢 Стоп",
        "en": "🟢 Stop"
    },
    "free_button": {
        "ru": "🎁 Бесплатно",
        "en": "🎁 Free"
    },
    "support_button": {
        "ru": "💬 Поддержка",
        "en": "💬 Support"
    },
    "invoice_title": {
        "ru": "Доступ к объявлениям",
        "en": "Access to announcements"
    },
    "invoice_description": {
        "ru": "Подписка на 30 дней",
        "en": "30-day subscription"
    },
    "invoice_label": {
        "ru": "Стоимость",
        "en": "Cost"
    },
    # Сообщения из webhook.py
    "settings_saved": {
        "ru": "✅ Настройки сохранены!\nГород: {city}\nРайоны: {districts}\nТип сделки: {deal_type}\nЦена: {price_from}-{price_to}$\nЭтаж: {floor_from}-{floor_to}\nКомнат: {rooms_from}-{rooms_to}\nСпален: {bedrooms_from}-{bedrooms_to}\nТолько собственник: {own_ads}",
        "en": "✅ Settings saved!\nCity: {city}\nDistricts: {districts}\nDeal type: {deal_type}\nPrice: {price_from}-{price_to}$\nFloor: {floor_from}-{floor_to}\nRooms: {rooms_from}-{rooms_to}\nBedrooms: {bedrooms_from}-{bedrooms_to}\nOwner only: {own_ads}"
    },
    "support_sent": {
        "ru": "✅ Ваше сообщение отправлено в поддержку. Мы ответим скоро!",
        "en": "✅ Your message has been sent to support. We will respond soon!"
    },
    "support_empty": {
        "ru": "❌ Ошибка: пустое сообщение. Попробуйте ещё раз.",
        "en": "❌ Error: empty message. Please try again."
    },
    "invalid_data": {
        "ru": "⚠️ Ошибка: Неверный формат данных WebApp",
        "en": "⚠️ Error: Invalid WebApp data format"
    },
    "unknown_type": {
        "ru": "❌ Неизвестный тип данных. Обратитесь в поддержку.",
        "en": "❌ Unknown data type. Contact support."
    },
    "processing_error": {
        "ru": "❌ Произошла ошибка при обработке запроса. Попробуйте снова.",
        "en": "❌ An error occurred while processing the request. Try again."
    },

    

    # Сообщения из support.py
    "support_reply": {
        "ru": "💬 Ответ поддержки:\n{reply}",
        "en": "💬 Support response:\n{reply}"
    },
    "support_reply_sent": {
        "ru": "✅ Ответ отправлен пользователю.",
        "en": "✅ Response sent to the user."
    },
    "support_empty_reply": {
        "ru": "❌ Пожалуйста, введите непустой текст ответа.",
        "en": "❌ Please enter a non-empty response text."
    },
    "support_reply_error": {
        "ru": "❌ Не удалось отправить сообщение пользователю: {error}",
        "en": "❌ Failed to send message to user: {error}"
    }
    
}