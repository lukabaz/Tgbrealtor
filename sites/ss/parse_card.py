import time
import random
import logging
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def parse_card(driver, url):
    time.sleep(random.uniform(3, 5))  # Ещё одна задержка перед загрузкой страницы
    driver.get(url)

    try: title = driver.find_element(By.CSS_SELECTOR, "h1").text
    except NoSuchElementException: title = "❌ Заголовок не найден"

    try: area = driver.find_element(By.XPATH, "//span[contains(text(), 'Площадь') or contains(text(), 'Area')]/following-sibling::span").text
    except NoSuchElementException: area = "❌ Площадь не найдена"

    try: rooms = driver.find_element(By.XPATH, "//span[contains(text(), 'Комната') or contains(text(), 'Rooms')]/following-sibling::span").text
    except NoSuchElementException: rooms = "❌ Комнаты не найдены"

    try: floor = driver.find_element(By.XPATH, "//span[contains(text(), 'этаж') or contains(text(), 'Floor')]/following-sibling::span").text
    except NoSuchElementException: floor = "❌ Этаж не найден"

    try: date = driver.find_element(By.CSS_SELECTOR, "div.flex.items-center.flex-shrink-0.order-1 span").text
    except NoSuchElementException: date = "❌ Дата не найдена"
    # try: ad_id = driver.find_element(By.XPATH, "//span[contains(text(), 'ID')]").text.split(":")[1].strip()
    # except NoSuchElementException: ad_id = "❌ ID не найден"
    try:
        sticky_container = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'col-span-3') and contains(@class, 'sticky')]"))
        )
        driver.execute_script("window.scrollBy(0, 150);")
        time.sleep(random.uniform(0.8, 1.5))

        try:
            price_container = sticky_container.find_element(By.XPATH, ".//div[contains(@class, 'font-tbcx-bold')]")
            spans = price_container.find_elements(By.TAG_NAME, "span")
            price = "".join(span.text for span in spans).strip()
        except NoSuchElementException:
            price = "❌ Цена не найдена"

        try:
            owner_tag = sticky_container.find_element(
                By.XPATH, ".//div[contains(text(), 'Собственник') or contains(text(), 'Агент') or contains(text(), 'Owner') or contains(text(), 'Agent')]"
            ).text
        except NoSuchElementException:
            owner_tag = "❌ Продавец не найден"

        # Телефон
        try:
            phone_span = sticky_container.find_element(
                By.XPATH, ".//button//span[contains(text(), '+995')]"
            )
            phone = phone_span.text.strip()
            print(f"Телефон сразу доступен: {phone}")
        except NoSuchElementException:
            try:
                phone_button = WebDriverWait(sticky_container, 7).until(
                    EC.element_to_be_clickable((By.XPATH, ".//button[.//span[starts-with(text(), 'Показать номер') or starts-with(text(), 'Show number')]])]]"))
                )
                print("Кнопка найдена.")
                time.sleep(random.uniform(0.8, 1.5))
                phone_button.click()
                time.sleep(random.uniform(0.8, 1.5))

                phone_span = WebDriverWait(sticky_container, 5).until(
                    EC.visibility_of_element_located((By.XPATH, ".//button//span[contains(text(), '+995')]"))
                )
                phone = phone_span.text.strip()
                print(f"Телефон успешно получен после клика: {phone}")
            except Exception as e:
                logging.warning(f"Не удалось получить номер телефона: {e}")
                phone = "❌ Телефон не найден"

        images = []
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.swiper-slide img")))
            img_elements = driver.find_elements(By.CSS_SELECTOR, "div.swiper-slide img")
            seen = set()
            for img in img_elements:
                src = img.get_attribute("src")
                if src and src not in seen:
                    seen.add(src)
                    images.append(src)
                    if len(images) == 2:  # ограничиваем до 2 ссылок
                        break
        except Exception as e:
            logging.warning(f"Ошибка при загрузке фото: {e}")
    except Exception as e:
        logging.warning(f"Ошибка при получении sticky контейнера или его содержимого: {e}")
        price = "❌ Цена не найдена"
        owner_tag = "❌ Продавец не найден"
        phone = "❌ Телефон не найден"
        images = []        

    logging.info("Объявление:")
    logging.info(f"Заголовок: {title}")
    logging.info(f"Цена: {price}")
    logging.info(f"Площадь: {area}")
    logging.info(f"Комнаты: {rooms}")
    logging.info(f"Этаж: {floor}")
    # logging.info(f"Дата публикации: {date}")
    logging.info(f"Телефон: {phone}")
    logging.info(f"Продавец: {owner_tag}")
    # logging.info(f"ID: {ad_id}")
    logging.info(f"Фото: {len(images)} шт.")
    for i, img in enumerate(images):
        logging.info(f"   [{i+1}] {img}")    

    print("📋 Объявление:")
    print("🔹 Заголовок:", title)
    print("💰 Цена:", price)
    print("📐 Площадь:", area)
    print("🚪 Комнаты:", rooms)
    print("🏢 Этаж:", floor)
    # print("📅 Дата публикации:", date)
    print("📞 Телефон:", phone)
    print("👤 Продавец:", owner_tag)
    # print("🆔 ID:", ad_id)
    print("🖼 Фото:", len(images), "шт.")
    for i, img in enumerate(images):
        print(f"   [{i+1}] {img}")
    print("-" * 40)

    return dict(
        title=title, price=price, area=area, rooms=rooms, floor=floor,
        date=date, phone=phone, owner_tag=owner_tag, link=url, images=images
    )
