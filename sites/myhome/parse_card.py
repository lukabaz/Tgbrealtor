import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from utils.logger import setup_logger

# Настройка логгера
logger = setup_logger("ss_parser", "logs/parser.log")

def parse_card(driver, url):
    """Парсинг карточки с сайта ss.ge"""
    logger.info(f"Parsing card: {url}")
    time.sleep(random.uniform(3, 5))
    driver.get(url)

    try:
        title = driver.find_element(By.CSS_SELECTOR, "h1").text
        logger.info(f"Extracted title: {title}")
    except NoSuchElementException:
        title = "❌ Заголовок не найден"
        logger.warning(f"Title not found for {url}")

    try:
        price = driver.find_element(By.CSS_SELECTOR, "div.price").text
        logger.info(f"Extracted price: {price}")
    except NoSuchElementException:
        price = "❌ Цена не найдена"
        logger.warning(f"Price not found for {url}")

    try:
        area = driver.find_element(By.XPATH, "//span[contains(text(), 'Area')]/following-sibling::span").text
        logger.info(f"Extracted area: {area}")
    except NoSuchElementException:
        area = "❌ Площадь не найдена"
        logger.warning(f"Area not found for {url}")

    try:
        rooms = driver.find_element(By.XPATH, "//span[contains(text(), 'Rooms')]/following-sibling::span").text
        logger.info(f"Extracted rooms: {rooms}")
    except NoSuchElementException:
        rooms = "❌ Комнаты не найдены"
        logger.warning(f"Rooms not found for {url}")

    try:
        floor = driver.find_element(By.XPATH, "//span[contains(text(), 'Floor')]/following-sibling::span").text
        logger.info(f"Extracted floor: {floor}")
    except NoSuchElementException:
        floor = "❌ Этаж не найден"
        logger.warning(f"Floor not found for {url}")

    try:
        date = driver.find_element(By.CSS_SELECTOR, "div.date").text
        logger.info(f"Extracted date: {date}")
    except NoSuchElementException:
        date = "❌ Дата не найдена"
        logger.warning(f"Date not found for {url}")

    try:
        owner_tag = driver.find_element(By.XPATH, "//div[contains(text(), 'Owner') or contains(text(), 'Agent')]").text
        logger.info(f"Extracted owner: {owner_tag}")
    except NoSuchElementException:
        owner_tag = "❌ Продавец не найден"
        logger.warning(f"Owner not found for {url}")

    try:
        phone = driver.find_element(By.XPATH, "//span[contains(text(), '+995')]").text
        logger.info(f"Extracted phone: {phone}")
    except NoSuchElementException:
        phone = "❌ Телефон не найден"
        logger.warning(f"Phone not found for {url}")

    images = []
    try:
        img_elements = driver.find_elements(By.CSS_SELECTOR, "img.property-image")
        seen = set()
        for img in img_elements:
            src = img.get_attribute("src")
            if src and src not in seen:
                seen.add(src)
                images.append(src)
                if len(images) == 2:
                    break
        logger.info(f"Extracted {len(images)} images")
        for i, img in enumerate(images):
            logger.info(f"Image [{i+1}]: {img}")
    except Exception as e:
        logger.warning(f"Error loading images: {e}")

    logger.info("Parsed advertisement:")
    logger.info(f"Title: {title}")
    logger.info(f"Price: {price}")
    logger.info(f"Area: {area}")
    logger.info(f"Rooms: {rooms}")
    logger.info(f"Floor: {floor}")
    logger.info(f"Date: {date}")
    logger.info(f"Phone: {phone}")
    logger.info(f"Owner: {owner_tag}")
    logger.info(f"Images: {len(images)} шт.")

    return dict(
        title=title,
        price=price,
        area=area,
        rooms=rooms,
        floor=floor,
        date=date,
        phone=phone,
        owner_tag=owner_tag,
        link=url,
        images=images
    )