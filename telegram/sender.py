import time
import requests
import logging
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from config import TELEGRAM_TOKEN

def format_card_message(card_data, lang="ru"):
    TRANSLATIONS = {
        "ru": {
            "title": "🏠",
            "price": "💵",
            "area": "📐 Площадь",
            "rooms": "🚪 Комнаты",
            "floor": "🏢 Этаж",
            "phone": "📞 Телефон",
            "owner": "👤 Продавец",
            "link": "🔗"
        },
        "en": {
            "title": "🏠",
            "price": "💵",
            "area": "📐 Area",
            "rooms": "🚪 Rooms",
            "floor": "🏢 Floor",
            "phone": "📞 Phone",
            "owner": "👤 Owner",
            "link": "🔗"
        }
    }
    t = TRANSLATIONS[lang]
    return (
        f"{t['title']} {card_data['title']}\n"
        f"{t['price']} {card_data['price']}\n"
        f"{t['area']}: {card_data['area']}\n"
        f"{t['rooms']}: {card_data['rooms']}\n"
        f"{t['floor']}: {card_data['floor']}\n"
        f"{t['phone']}: {card_data['phone']}\n"
        f"{t['owner']}: {card_data['owner_tag']}\n"
        f"{t['link']} {card_data['link']}"
    )

def send_to_telegram(chat_id, card_data):
    lang = "en" if "/en/" in card_data.get("link", "") else "ru"
    message = format_card_message(card_data, lang)
    images = card_data.get("images", [])

    if images:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        payload = {
            "chat_id": chat_id,
            "photo": images[0],
            "caption": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            logging.info(f"📤 Фото отправлено в Telegram (chat_id {chat_id})")
            time.sleep(1)
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка отправки фото: {e}")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"📤 Сообщение отправлено в Telegram (chat_id {chat_id})")
        time.sleep(1)
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка отправки сообщения: {e}")
        return False