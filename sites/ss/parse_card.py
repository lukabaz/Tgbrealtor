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
    time.sleep(random.uniform(3, 5))  # Задержка перед загрузкой страницы
    driver.get(url)

    try:
        title = driver.find_element(By.CSS_SELECTOR, "h1.listing-title").text
        logger.info(f"Extracted title: {title}")
    except NoSuchElementException:
        title = "❌ Заголовок не найден"
        logger.warning(f"Title not found for {url}")

    try:
        area = driver.find_element(By.XPATH, "//div[contains(text(), 'ფართი') or contains(text(), 'Area')]/following-sibling::div").text
        logger.info(f"Extracted area: {area}")
    except NoSuchElementException:
        area = "❌ Площадь не найдена"
        logger.warning(f"Area not found for {url}")

    try:
        rooms = driver.find_element(By.XPATH, "//div[contains(text(), 'ოთახები') or contains(text(), 'Rooms')]/following-sibling::div").text
        logger.info(f"Extracted rooms: {rooms}")
    except NoSuchElementException:
        rooms = "❌ Комнаты не найдены"
        logger.warning(f"Rooms not found for {url}")

    try:
        floor = driver.find_element(By.XPATH, "//div[contains(text(), 'სართული') or contains(text(), 'Floor')]/following-sibling::div").text
        logger.info(f"Extracted floor: {floor}")
    except NoSuchElementException:
        floor = "❌ Этаж не найден"
        logger.warning(f"Floor not found for {url}")

    try:
        date = driver.find_element(By.CSS_SELECTOR, "div.date-published").text
        logger.info(f"Extracted date: {date}")
    except NoSuchElementException:
        date = "❌ Дата не найдена"
        logger.warning(f"Date not found for {url}")

    try:
        sticky_container = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'listing-sidebar')]"))
        )
        driver.execute_script("window.scrollBy(0, 150);")
        time.sleep(random.uniform(0.8, 1.5))

        try:
            price_container = sticky_container.find_element(By.CSS_SELECTOR, "div.price-amount")
            price = price_container.text.strip()
            logger.info(f"Extracted price: {price}")
        except NoSuchElementException:
            price = "❌ Цена не найдена"
            logger.warning(f"Price not found for {url}")

        try:
            owner_tag = sticky_container.find_element(
                By.XPATH, ".//div[contains(text(), 'მფლობელი') or contains(text(), 'აგენტი') or contains(text(), 'Owner') or contains(text(), 'Agent')]"
            ).text
            logger.info(f"Extracted owner: {owner_tag}")
        except NoSuchElementException:
            owner_tag = "❌ Продавец не найден"
            logger.warning(f"Owner not found for {url}")

        try:
            phone_span = sticky_container.find_element(
                By.XPATH, ".//a[contains(@href, 'tel:+995')]"
            )
            phone = phone_span.text.strip()
            logger.info(f"Phone immediately available: {phone}")
        except NoSuchElementException:
            try:
                phone_button = WebDriverWait(sticky_container, 7).until(
                    EC.element_to_be_clickable((By.XPATH, ".//button[contains(text(), 'ნომრის ჩვენება') or contains(text(), 'Show number')]"))
                )
                logger.info("Phone button found")
                time.sleep(random.uniform(0.8, 1.5))
                phone_button.click()
                time.sleep(random.uniform(0.8, 1.5))

                phone_span = WebDriverWait(sticky_container, 5).until(
                    EC.visibility_of_element_located((By.XPATH, ".//a[contains(@href, 'tel:+995')]"))
                )
                phone = phone_span.text.strip()
                logger.info(f"Phone successfully retrieved after click: {phone}")
            except Exception as e:
                phone = "❌ Телефон не найден"
                logger.warning(f"Failed to retrieve phone number: {e}")

        images = []
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.image-gallery img")))
            img_elements = driver.find_elements(By.CSS_SELECTOR, "div.image-gallery img")
            seen = set()
            for img in img_elements:
                src = img.get_attribute("src")
                if src and src not in seen:
                    seen.add(src)
                    images.append(src)
                    if len(images) == 2:  # Ограничиваем до 2 ссылок
                        break
            logger.info(f"Extracted {len(images)} images")
            for i, img in enumerate(images):
                logger.info(f"Image [{i+1}]: {img}")
        except Exception as e:
            logger.warning(f"Error loading images: {e}")

    except Exception as e:
        logger.warning(f"Error processing sidebar or its contents: {e}")
        price = "❌ Цена не найдена"
        owner_tag = "❌ Продавец не найден"
        phone = "❌ Телефон не найден"
        images = []

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