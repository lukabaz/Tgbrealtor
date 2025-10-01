# app.py
import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, PreCheckoutQueryHandler, ChatMemberHandler, Dispatcher
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from config import TELEGRAM_TOKEN, WEBHOOK_URL
from authorization.subscription import welcome_new_user, handle_buttons, successful_payment, pre_checkout
from authorization.webhook import webhook_update
from authorization.support import handle_user_message
from utils.redis_client import redis_client
from sites.router import get_parse_function
from utils.driver import init_driver
from tg.sender import send_to_telegram
import time
import random
import logging
from datetime import datetime, timezone, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# Настройка логирования
logging.basicConfig(filename="app.log", level=logging.INFO, format="%(asctime)s - %(message)s", encoding="utf-8")

# Flask приложение
app = Flask(__name__)

# Инициализация Telegram бота
bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
dispatcher = Dispatcher(bot_app.bot, None, workers=0)

# Handlers для бота
bot_app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webhook_update))
bot_app.add_handler(ChatMemberHandler(welcome_new_user, ChatMemberHandler.MY_CHAT_MEMBER))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
bot_app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment)) 
bot_app.add_handler(PreCheckoutQueryHandler(pre_checkout))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_user_message))

# Health check endpoint для Render
@app.route('/healthz')
def healthz():
    return 'ok', 200

# Webhook endpoint
@app.route(f"/{TELEGRAM_TOKEN}", methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_app.bot)
    dispatcher.process_update(update)
    return 'ok'

# Логика парсера (из parser.py)
def close_modal_if_exists(driver):
    logging.info("Проверяем наличие модального окна")
    try:
        modal_close = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Закрыть')]"))
        )
        modal_close.click()
        logging.info("Модальное окно закрыто")
    except Exception as e:
        logging.debug(f"Модальное окно не найдено: {e}")
    finally:
        logging.info("Проверка модального окна завершена")

def wait_for_cards(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.group.relative.block.overflow-hidden.rounded-xl.shadow-devCard"))
        )
        logging.info("Карточки загружены")
    except TimeoutException as e:
        logging.warning(f"Карточки не загрузились в течение {timeout} секунд: {e}")
        raise

def open_page(driver, url):
    logging.info(f"Открываем страницу: {url}")
    time.sleep(random.uniform(1, 3))
    driver.get(url)
    time.sleep(random.uniform(3, 5))
    close_modal_if_exists(driver)
    wait_for_cards(driver)
    time.sleep(2)

def parse_date(date_str):
    try:
        months = {
            "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
            "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12
        }
        parts = date_str.replace(".", "").split()
        if len(parts) != 3:
            logging.warning(f"Некорректный формат даты: {date_str}")
            return 0
        day, month_str, time_part = parts
        day = int(day)
        month = months.get(month_str.lower()[:3])
        if not month:
            logging.warning(f"Неизвестный месяц: {month_str}")
            return 0
        hour, minute = map(int, time_part.split(":"))
        current_date = datetime.now(timezone.utc)
        current_year = current_date.year
        current_month = current_date.month
        current_day = current_date.day
        if month < current_month or (month == current_month and day <= current_day):
            year = current_year
        else:
            year = current_year - 1
        dt_get = datetime(year, month, day, hour, minute)
        dt_utc = dt_get - timedelta(hours=4)
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        return int(dt_utc.timestamp())
    except Exception as e:
        logging.error(f"Ошибка парсинга даты '{date_str}': {e}")
        return 0

def get_card_status(card):
    try:
        status_span = card.find_element(By.CSS_SELECTOR, "div.ml-2.mt-2.flex.gap-1\\.5 span")
        status = status_span.text.strip()
        if status in ["S-VIP", "VIP+", "VIP"]:
            return status
        return "normal"
    except NoSuchElementException:
        return "normal"

def has_date_element(card):
    try:
        card.find_element(By.CSS_SELECTOR, "div.flex.justify-between.break-all.mb-\\[18px\\].md\\:mb-5.mt-3.md\\:mt-3\\.5.px-4 > div.flex.items-center.h-full.gap-1.text-secondary-70.text-xs > span")
        return True
    except NoSuchElementException:
        return False

def is_valid_card_href(card):
    try:
        href = card.get_attribute("href")
        if href and href.startswith("https://www.myhome.ge/ru/pr/"):
            return True
        if href and href.startswith("https://auction.livo.ge/"):
            logging.info(f"Карточка исключена: href={href} (аукционная карточка)")
            return False
        return False
    except Exception as e:
        logging.warning(f"Ошибка проверки href карточки: {e}")
        return False

def run_parser():
    current_timestamp = int(time.time())
    active_users = []
    for key in redis_client.scan_iter("user:*"):
        user_data = {k: v for k, v in redis_client.hgetall(key).items()}
        chat_id = key.split(":")[1]
        subscription_end = int(user_data.get("subscription_end", 0))
        if not subscription_end or subscription_end < current_timestamp:
            continue
        if user_data.get("bot_status") != "running":
            continue
        if not user_data.get("filters_url"):
            logging.error(f"filters_url для chat_id {chat_id} не найден в Redis")
            continue
        if not user_data.get("filters_timestamp"):
            logging.warning(f"filters_timestamp для chat_id {chat_id} не найден, пропускаем")
            continue
        active_users.append({
            "chat_id": chat_id,
            "url": user_data["filters_url"],
            "filters_timestamp": int(user_data["filters_timestamp"]),
            "last_sent_timestamp": int(user_data.get("last_sent_timestamp", 0))
        })

    logging.info(f"Найдено активных пользователей: {len(active_users)}")
    print(f"👥 Найдено активных пользователей: {len(active_users)}")
    for user in active_users:
        logging.info(f"chat_id: {user['chat_id']}, URL: {user['url']}, filters_timestamp: {user['filters_timestamp']}, last_sent_timestamp: {user['last_sent_timestamp']}")
        print(f"chat_id: {user['chat_id']}, URL: {user['url']}, filters_timestamp: {user['filters_timestamp']}, last_sent_timestamp: {user['last_sent_timestamp']}")

    driver = init_driver(headless=True)
    try:
        for user in active_users:
            logging.info(f"Обрабатываем пользователя: chat_id {user['chat_id']}")
            print(f"👤 Обрабатываем пользователя: chat_id {user['chat_id']}")
            page_number = 1
            threshold_timestamp = max(user["filters_timestamp"], user["last_sent_timestamp"])
            seen_statuses = {"S-VIP": False, "VIP+": False, "VIP": False, "normal": False}
            encountered_statuses = {"S-VIP": False, "VIP+": False, "VIP": False, "normal": False}
            links_to_process = []
            timestamps = {}

            while True:
                current_url = user["url"]
                if "page=" in current_url:
                    current_url = current_url.rsplit("page=", 1)[0] + f"page={page_number}"
                else:
                    current_url = user["url"] + f"&page={page_number}"
                logging.info(f"Открываем страницу {page_number}: {current_url}")
                print(f"📄 Открываем страницу {page_number}: {current_url}")
                open_page(driver, current_url)
                cards = driver.find_elements(By.CSS_SELECTOR, "a.group.relative.block.overflow-hidden.rounded-xl.shadow-devCard")
                if not cards:
                    logging.info("Карточки на странице не найдены, завершаем пагинацию")
                    print("🛑 Карточки на странице не найдены, завершаем пагинацию")
                    break
                logging.info(f"Найдено элементов (потенциальных карточек) на странице {page_number}: {len(cards)}")
                print(f"🧩 Найдено элементов (потенциальных карточек) на странице {page_number}: {len(cards)}")
                valid_cards = [card for card in cards if has_date_element(card) and is_valid_card_href(card)]
                logging.info(f"Найдено валидных карточек (с датой и корректным href) на странице {page_number}: {len(valid_cards)}")
                print(f"✅ Найдено валидных карточек (с датой и корректным href) на странице {page_number}: {len(valid_cards)}")
                stop_pagination = False
                for i, card in enumerate(valid_cards):
                    try:
                        status = get_card_status(card)
                        logging.info(f"Карточка {i+1} (страница {page_number}): Статус: {status}")
                        print(f"🔖 Карточка {i+1} (страница {page_number}): Статус: {status}")
                        encountered_statuses[status] = True
                        date_elem = WebDriverWait(card, 15).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR,
                                "div.flex.justify-between.break-all.mb-\\[18px\\].md\\:mb-5.mt-3.md\\:mt-3\\.5.px-4 > div.flex.items-center.h-full.gap-1.text-secondary-70.text-xs > span"
                            ))
                        )
                        date_str = date_elem.text.strip()
                        print(f"📅 Карточка {i+1} (страница {page_number}): Сырые данные даты: '{date_str}'")
                        date_timestamp = parse_date(date_str)
                        logging.info(f"Карточка {i+1} (страница {page_number}): Дата: {date_str}, Timestamp: {date_timestamp}")
                        print(f"📅 Карточка {i+1} (страница {page_number}): Дата: {date_str}, Timestamp: {date_timestamp}")
                        if date_timestamp <= threshold_timestamp:
                            logging.info(f"⏩ Карточка {i+1} (страница {page_number}) пропущена (дата {date_timestamp} <= {threshold_timestamp})")
                            print(f"⏩ Карточка {i+1} (страница {page_number}) пропущена (дата {date_timestamp} <= {threshold_timestamp})")
                            seen_statuses[status] = True
                            if status == "normal":
                                seen_statuses["S-VIP"] = True
                                seen_statuses["VIP+"] = True
                                seen_statuses["VIP"] = True
                                logging.info(f"Обычная карточка с датой {date_timestamp} <= {threshold_timestamp}, дальнейшие карточки будут старше, завершаем пагинацию")
                                print(f"🛑 Обычная карточка с датой {date_timestamp} <= {threshold_timestamp}, дальнейшие карточки будут старше, завершаем пагинацию")
                                stop_pagination = True
                                break
                        else:
                            href = card.get_attribute("href")
                            if not href:
                                logging.error(f"Не удалось извлечь href для карточки {i+1} (страница {page_number})")
                                continue
                            links_to_process.append(href)
                            timestamps[href] = date_timestamp
                    except Exception as e:
                        logging.error(f"❌ Ошибка извлечения данных для карточки {i+1} (страница {page_number}): {e}")
                        print(f"❌ Ошибка извлечения данных для карточки {i+1} (страница {page_number}): {e}")
                if stop_pagination:
                    break
                if page_number == 1:
                    for status in encountered_statuses:
                        if not encountered_statuses[status]:
                            logging.info(f"Статус {status} отсутствует, помечаем как обработанный")
                            print(f"🔖 Статус {status} отсутствует, помечаем как обработанный")
                            seen_statuses[status] = True
                all_processed = True
                for status in encountered_statuses:
                    if encountered_statuses[status] and not seen_statuses[status]:
                        all_processed = False
                        break
                if all_processed and not links_to_process:
                    logging.info(f"Все статусы обработаны, завершаем пагинацию для пользователя {user['chat_id']} на странице {page_number}")
                    print(f"🛑 Все статусы обработаны, завершаем пагинацию для пользователя {user['chat_id']} на странице {page_number}")
                    break
                try:
                    next_page = driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
                    if "disabled" in next_page.get_attribute("class"):
                        logging.info("Кнопка 'Следующая страница' неактивна, завершаем пагинацию")
                        print("🛑 Кнопка 'Следующая страница' неактивна, завершаем пагинацию")
                        break
                    page_number += 1
                except NoSuchElementException:
                    logging.info("Кнопка 'Следующая страница' не найдена, завершаем пагинацию")
                    print("🛑 Кнопка 'Следующая страница' не найдена, завершаем пагинацию")
                    break
            logging.info(f"Собрано ссылок для обработки: {len(links_to_process)} для chat_id {user['chat_id']}")
            print(f"🔗 Собрано ссылок для обработки: {len(links_to_process)} для chat_id {user['chat_id']}")
            for i, href in enumerate(links_to_process):
                try:
                    logging.info(f"Обрабатываем ссылку {i+1}/{len(links_to_process)}: {href}")
                    print(f"🔍 Обрабатываем ссылку {i+1}/{len(links_to_process)}: {href}")
                    parse_card = get_parse_function(href)
                    card_data = parse_card(driver, href)
                    if not card_data:
                        logging.error(f"Не удалось извлечь данные для ссылки {href}")
                        continue
                    send_to_telegram(user["chat_id"], card_data)
                    date_timestamp = timestamps.get(href, 0)
                    latest_timestamp = max(threshold_timestamp, date_timestamp)
                    if latest_timestamp > threshold_timestamp:
                        # redis_client.hset(f"user:{chat_id}", "last_sent_timestamp", int(time.time()))
                        redis_client.hset(f"user:{user['chat_id']}", "last_sent_timestamp", int(time.time()))
                        logging.info(f"Обновлен last_sent_timestamp для chat_id {user['chat_id']}: {latest_timestamp}")
                        print(f"⏰ Обновлен last_sent_timestamp для chat_id {user['chat_id']}: {latest_timestamp}")
                except Exception as e:
                    logging.error(f"❌ Ошибка обработки ссылки {href}: {e}")
                    print(f"❌ Ошибка обработки ссылки {href}: {e}")
    except Exception as e:
        logging.error(f"Ошибка парсинга: {e}")
        print(f"❌ Ошибка парсинга: {e}")
        bot_app.bot.send_message(chat_id='6770986953', text=f"Ошибка парсера: {e}")
    finally:
        driver.quit()
    logging.info("Парсер завершил цикл")
    print("✅ Парсер завершил цикл")

# Scheduler для парсера
scheduler = BackgroundScheduler()
scheduler.add_job(run_parser, IntervalTrigger(minutes=5))
scheduler.start()

if __name__ == "__main__":
    # Устанавливаем webhook при старте
    bot_app.bot.set_webhook(url=WEBHOOK_URL)
    # Запускаем Flask
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))     