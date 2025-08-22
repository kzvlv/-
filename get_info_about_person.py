import time
from selenium import webdriver
import selenium  # полностью импортируем библиотеку
from selenium.webdriver.common.by import By  # подключаем определенную функцию из библиотеки


with open('resource\\FedRes_login.txt', 'r', encoding='utf-8') as file:
    FedRes_login = file.read()
with open('resource\\FedRes_password.txt', 'r', encoding='utf-8') as file:
    FedRes_password = file.read()
# --- Selenium часть ---
# Инициализация веб-драйвера

try:
    driver = webdriver.Chrome()
    driver.get("https://old.bankrot.fedresurs.ru/BackOffice/ArbitrManager/MessagesList.aspx")  # Открываем страницу

    login_input = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_ctplhMain_Login1_UserName')  # находим элемент по селектору
    login_input.clear()  # очищаем поле для ввода
    login_input.send_keys(FedRes_login)  # вводим логин

    password_input = driver.find_element(By.CSS_SELECTOR,
                                         '#ctl00_ctplhMain_Login1_Password')  # находим элемент по селектору
    password_input.clear()  # очищаем поле для ввода
    password_input.send_keys(FedRes_password)  # вводим логин

    next_button = driver.find_element(By.CSS_SELECTOR, '#ctl00_ctplhMain_agreement')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_ctplhMain_Login1_RememberMe')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_ctplhMain_Login1_LoginImageButton')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    time.sleep(10)  # вход на сайт

except Exception as e:
    print(f"Не удалось запустить Selenium. Ошибка: {e}")
    print("Продолжаем работу без части с браузером.")