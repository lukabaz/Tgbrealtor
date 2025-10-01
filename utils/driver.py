from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def init_driver(headless=True):
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-notifications")  # Добавьте эту строку
    chrome_options.add_argument("--no-sandbox")  # Добавить
    chrome_options.add_argument("--disable-dev-shm-usage")  # Добавить
    #chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
    #chrome_options.add_argument("--window-size=1920,1080")
    if headless:
        chrome_options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=chrome_options)
    return driver
