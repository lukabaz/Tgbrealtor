# parser.py - Selenium Parser Process
import signal
import sys
import time
import random
import logging
import os
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

from utils.redis_client import redis_client
from sites.router import get_parse_function
from utils.driver import init_driver
from tg.sender import send_to_telegram

# Создаем директорию для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования для парсера
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/parser.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("selenium_parser")

class SeleniumParser:
    def __init__(self):
        self.scheduler = None
        self.running = False
        
    def close_modal_if_exists(self, driver):
        """Закрытие модального окна если существует"""
        logger.info("Проверяем наличие модального окна")
        try:
            modal_close = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Закрыть')]"))
            )
            modal_close.click()
            logger.info("Модальное окно закрыто")
        except Exception as e:
            logger.debug(f"Модальное окно не найдено: {e}")
        finally:
            logger.info("Проверка модального окна завершена")

    def wait_for_cards(self, driver, timeout=10):
        """Ожидание загрузки карточек"""
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a.group.relative.block.overflow-hidden.rounded-xl.shadow-devCard"))
            )
            logger.info("Карточки загружены")
        except TimeoutException as e:
            logger.warning(f"Карточки не загрузились в течение {timeout} секунд: {e}")
            raise

    def open_page(self, driver, url):
        """Открытие страницы с обработкой модальных окон"""
        logger.info(f"Открываем страницу: {url}")
        time.sleep(random.uniform(1, 3))
        driver.get(url)
        time.sleep(random.uniform(3, 5))
        self.close_modal_if_exists(driver)
        self.wait_for_cards(driver)
        time.sleep(2)

    def parse_date(self, date_str):
        """Парсинг даты из строки"""
        try:
            months = {
                "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5, "июн": 6,
                "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12
            }
            parts = date_str.replace(".", "").split()
            if len(parts) != 3:
                logger.warning(f"Некорректный формат даты: {date_str}")
                return 0
            day, month_str, time_part = parts
            day = int(day)
            month = months.get(month_str.lower()[:3])
            if not month:
                logger.warning(f"Неизвестный месяц: {month_str}")
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
            logger.error(f"Ошибка парсинга даты '{date_str}': {e}")
            return 0

    def get_card_status(self, card):
        """Получение статуса карточки"""
        try:
            status_span = card.find_element(By.CSS_SELECTOR, "div.ml-2.mt-2.flex.gap-1\\.5 span")
            status = status_span.text.strip()
            if status in ["S-VIP", "VIP+", "VIP"]:
                return status
            return "normal"
        except NoSuchElementException:
            return "normal"

    def has_date_element(self, card):
        """Проверка наличия элемента даты в карточке"""
        try:
            card.find_element(By.CSS_SELECTOR, "div.flex.justify-between.break-all.mb-\\[18px\\].md\\:mb-5.mt-3.md\\:mt-3\\.5.px-4 > div.flex.items-center.h-full.gap-1.text-secondary-70.text-xs > span")
            return True
        except NoSuchElementException:
            return False

    def is_valid_card_href(self, card):
        """Проверка валидности ссылки карточки"""
        try:
            href = card.get_attribute("href")
            if href and href.startswith("https://www.myhome.ge/ru/pr/"):
                return True
            if href and href.startswith("https://auction.livo.ge/"):
                logger.info(f"Карточка исключена: href={href} (аукционная карточка)")
                return False
            return False
        except Exception as e:
            logger.warning(f"Ошибка проверки href карточки: {e}")
            return False

    def run_parser(self):
        """Основная функция парсинга"""
        logger.info("🚀 run_parser() triggered")
        current_timestamp = int(time.time())
        active_users = []
        
        # Получение активных пользователей
        for key in redis_client.scan_iter("user:*"):
            user_data = {k: v for k, v in redis_client.hgetall(key).items()}
            chat_id = key.split(":")[1]
            subscription_end = int(user_data.get("subscription_end", 0))
            if not subscription_end or subscription_end < current_timestamp:
                continue
            if user_data.get("bot_status") != "running":
                continue
            if not user_data.get("filters_url"):
                logger.error(f"filters_url для chat_id {chat_id} не найден в Redis")
                continue
            if not user_data.get("filters_timestamp"):
                logger.warning(f"filters_timestamp для chat_id {chat_id} не найден, пропускаем")
                continue
            active_users.append({
                "chat_id": chat_id,
                "url": user_data["filters_url"],
                "filters_timestamp": int(user_data["filters_timestamp"]),
                "last_sent_timestamp": int(user_data.get("last_sent_timestamp", 0))
            })

        logger.info(f"Найдено активных пользователей: {len(active_users)}")
        
        if not active_users:
            logger.info("Нет активных пользователей для парсинга")
            return

        driver = init_driver(headless=True)
        try:
            for user in active_users:
                logger.info(f"Обрабатываем пользователя: chat_id {user['chat_id']}")
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
                    
                    logger.info(f"Открываем страницу {page_number}: {current_url}")
                    self.open_page(driver, current_url)
                    cards = driver.find_elements(By.CSS_SELECTOR, "a.group.relative.block.overflow-hidden.rounded-xl.shadow-devCard")
                    
                    if not cards:
                        logger.info("Карточки на странице не найдены, завершаем пагинацию")
                        break
                        
                    logger.info(f"Найдено элементов (потенциальных карточек) на странице {page_number}: {len(cards)}")
                    valid_cards = [card for card in cards if self.has_date_element(card) and self.is_valid_card_href(card)]
                    logger.info(f"Найдено валидных карточек (с датой и корректным href) на странице {page_number}: {len(valid_cards)}")
                    
                    stop_pagination = False
                    for i, card in enumerate(valid_cards):
                        try:
                            status = self.get_card_status(card)
                            logger.info(f"Карточка {i+1} (страница {page_number}): Статус: {status}")
                            encountered_statuses[status] = True
                            
                            date_elem = WebDriverWait(card, 15).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR,
                                    "div.flex.justify-between.break-all.mb-\\[18px\\].md\\:mb-5.mt-3.md\\:mt-3\\.5.px-4 > div.flex.items-center.h-full.gap-1.text-secondary-70.text-xs > span"
                                ))
                            )
                            date_str = date_elem.text.strip()
                            date_timestamp = self.parse_date(date_str)
                            logger.info(f"Карточка {i+1} (страница {page_number}): Дата: {date_str}, Timestamp: {date_timestamp}")
                            
                            if date_timestamp <= threshold_timestamp:
                                logger.info(f"⏩ Карточка {i+1} (страница {page_number}) пропущена (дата {date_timestamp} <= {threshold_timestamp})")
                                seen_statuses[status] = True
                                if status == "normal":
                                    seen_statuses["S-VIP"] = True
                                    seen_statuses["VIP+"] = True
                                    seen_statuses["VIP"] = True
                                    logger.info(f"Обычная карточка с датой {date_timestamp} <= {threshold_timestamp}, дальнейшие карточки будут старше, завершаем пагинацию")
                                    stop_pagination = True
                                    break
                            else:
                                href = card.get_attribute("href")
                                if not href:
                                    logger.error(f"Не удалось извлечь href для карточки {i+1} (страница {page_number})")
                                    continue
                                links_to_process.append(href)
                                timestamps[href] = date_timestamp
                        except Exception as e:
                            logger.error(f"❌ Ошибка извлечения данных для карточки {i+1} (страница {page_number}): {e}")
                    
                    if stop_pagination:
                        break
                        
                    if page_number == 1:
                        for status in encountered_statuses:
                            if not encountered_statuses[status]:
                                logger.info(f"Статус {status} отсутствует, помечаем как обработанный")
                                seen_statuses[status] = True
                    
                    all_processed = True
                    for status in encountered_statuses:
                        if encountered_statuses[status] and not seen_statuses[status]:
                            all_processed = False
                            break
                    
                    if all_processed and not links_to_process:
                        logger.info(f"Все статусы обработаны, завершаем пагинацию для пользователя {user['chat_id']} на странице {page_number}")
                        break
                    
                    try:
                        next_page = driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next page']")
                        if "disabled" in next_page.get_attribute("class"):
                            logger.info("Кнопка 'Следующая страница' неактивна, завершаем пагинацию")
                            break
                        page_number += 1
                    except NoSuchElementException:
                        logger.info("Кнопка 'Следующая страница' не найдена, завершаем пагинацию")
                        break

                logger.info(f"Собрано ссылок для обработки: {len(links_to_process)} для chat_id {user['chat_id']}")
                
                # Обработка собранных ссылок
                for i, href in enumerate(links_to_process):
                    try:
                        logger.info(f"Обрабатываем ссылку {i+1}/{len(links_to_process)}: {href}")
                        parse_card = get_parse_function(href)
                        card_data = parse_card(driver, href)
                        if not card_data:
                            logger.error(f"Не удалось извлечь данные для ссылки {href}")
                            continue
                        send_to_telegram(user["chat_id"], card_data)
                        date_timestamp = timestamps.get(href, 0)
                        latest_timestamp = max(threshold_timestamp, date_timestamp)
                        if latest_timestamp > threshold_timestamp:
                            redis_client.hset(f"user:{user['chat_id']}", "last_sent_timestamp", int(time.time()))
                            logger.info(f"Обновлен last_sent_timestamp для chat_id {user['chat_id']}: {latest_timestamp}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка обработки ссылки {href}: {e}")
                        
        except Exception as e:
            logger.error(f"Ошибка парсинга: {e}")
        finally:
            driver.quit()

        logger.info("✅ Парсер завершил цикл")

    def signal_handler(self, signum, frame):
        """Graceful shutdown handler"""
        logger.info(f"Received signal {signum}, shutting down parser gracefully...")
        self.running = False
        if self.scheduler:
            logger.info("Shutting down scheduler...")
            self.scheduler.shutdown(wait=True)
        sys.exit(0)

    def run(self):
        """Запуск парсера с планировщиком"""
        try:
            # Настройка обработчиков сигналов для graceful shutdown
            signal.signal(signal.SIGTERM, self.signal_handler)
            signal.signal(signal.SIGINT, self.signal_handler)
            
            self.running = True
            
            # Создаем планировщик
            self.scheduler = BlockingScheduler()
            self.scheduler.add_job(
                self.run_parser, 
                IntervalTrigger(minutes=6),
                id='parser_job',
                max_instances=1,
                coalesce=True
            )
            
            logger.info("✅ Scheduler configured successfully")
            logger.info(f"🔁 Jobs in scheduler: {self.scheduler.get_jobs()}")
            
            # Запуск первого парсинга сразу
            logger.info("🚀 Running initial parse...")
            self.run_parser()
            
            # Запуск планировщика
            logger.info("🚀 Starting scheduler...")
            self.scheduler.start()
            
        except Exception as e:
            logger.error(f"❌ Error starting parser: {e}")
            raise

if __name__ == "__main__":
    parser = SeleniumParser()
    parser.run()
