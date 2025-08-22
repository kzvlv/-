import time
from selenium import webdriver
import selenium  # полностью импортируем библиотеку
from selenium.webdriver.common.by import By  # подключаем определенную функцию из библиотеки
import os
import json
import PyPDF2
import io
import requests
from datetime import datetime, timedelta
from selenium.webdriver.chrome.options import Options
import glob
import re

# Настройка Chrome для скачивания в нужную папку
chrome_options = Options()
download_dir = os.path.join(os.getcwd(), "downloads")  # Папка для загрузок
# Создаем папку если не существует
os.makedirs(download_dir, exist_ok=True)
# Настройки для скачивания
chrome_options.add_experimental_option("prefs", {
    "download.default_directory": download_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.always_open_pdf_externally": True,  # Важно: скачивать PDF, а не открывать
    "safebrowsing.enabled": True
})

driver = webdriver.Chrome(options=chrome_options)

# Текущая дата
current_date = datetime.now().strftime('%d.%m.%Y')

# Дата 3 года назад
three_years_ago = (datetime.now() - timedelta(days=365*3)).strftime('%d.%m.%Y')

def simple_txt_to_json(input_file, output_file):
    """Простой вариант преобразования для фиксированной структуры"""
    data = {}

    with open(input_file, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    for line in lines:
        line = line.strip()
        if ':' in line:
            key, value = line.split(':', 1)
            data[key.strip()] = value.strip()

    with open(output_file, 'w', encoding='utf-8') as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=2)

    return data

with open('resource\\FedRes_login.txt', 'r', encoding='utf-8') as file:
    FedRes_login = file.read()
with open('resource\\FedRes_password.txt', 'r', encoding='utf-8') as file:
    FedRes_password = file.read()
# --- Selenium часть ---
# Инициализация веб-драйвера

def wait_for_download_complete(directory, timeout=30):
    """Ждет пока файл полностью скачается"""
    seconds = 0
    while seconds < timeout:
        # Ищем временные файлы Chrome (.crdownload)
        temp_files = glob.glob(os.path.join(directory, "*.crdownload"))
        if not temp_files:
            # Ищем PDF файлы
            pdf_files = glob.glob(os.path.join(directory, "*.pdf"))
            if pdf_files:
                return pdf_files[0]  # Возвращаем путь к скачанному файлу
        time.sleep(1)
        seconds += 1
    return None


people_path = 'people'

# Получаем все элементы в папке
items = os.listdir(people_path)

# Ищем первую папку
for item in items:
    item_path = os.path.join(people_path, item)
    if os.path.isdir(item_path):
        folder_name = item
        break


Last_name, Name, Middle_name = folder_name.split()[0], folder_name.split()[1], folder_name.split()[2]

try:
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

    time.sleep(3)  # вход на сайт

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_MessageListControl_MessageFilterUpdatePanel > table > tbody > tr > td:nth-child(2) > img')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    time.sleep(2)

    driver.switch_to.frame(0)  # переключаемся на новое окно

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_cplhContent_InsolventList_radTs > div > ul > li.rtsLI.rtsLast > a > span > span > span')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    time.sleep(1)

    txt_input = driver.find_element(By.CSS_SELECTOR,
                                    '#ctl00_cplhContent_InsolventList_tbLastNameEgrip')  # # находим элемент по селектору
    txt_input.clear()  # отчищаем поле для ввода
    txt_input.send_keys(Last_name)  # вводим текст

    txt_input = driver.find_element(By.CSS_SELECTOR,
                                    '#ctl00_cplhContent_InsolventList_tbFirstNameEgrip')  # # находим элемент по селектору
    txt_input.clear()  # отчищаем поле для ввода
    txt_input.send_keys(Name)  # вводим текст

    txt_input = driver.find_element(By.CSS_SELECTOR,
                                    '#ctl00_cplhContent_InsolventList_tbMiddleNameEgrip')  # # находим элемент по селектору
    txt_input.clear()  # отчищаем поле для ввода
    txt_input.send_keys(Middle_name)  # вводим текст

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_cplhContent_InsolventList_btnSearchEgrip')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    time.sleep(2)

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#resultTable > tbody > tr:nth-child(2) > td:nth-child(2)')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    driver.switch_to.default_content()  # переключаемся на основное окно

    # УРОК 2

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#right > table > tbody > tr > td > table > tbody > tr > td:nth-child(1) > table > tbody > tr:nth-child(2) > td:nth-child(2) > table > tbody > tr:nth-child(2) > td:nth-child(2) > table > tbody > tr > td:nth-child(2) > img')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    driver.switch_to.frame(0)  # переключаемся на новое окно

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_cplhContent_MessageTypeTree > ul > li.rtLI.rtFirst > div > span.rtIn')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    driver.switch_to.default_content()  # переключаемся на основное окно

    time.sleep(0.5)

    next_button = driver.find_element(By.CSS_SELECTOR,
                                      '#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_MessageListControl_RefreshButton')  # находим элемент по селектору
    next_button.click()  # нажимаем кнопку

    time.sleep(1.5)

    cnt = 2

    while cnt != 0:
        next_button = driver.find_element(By.CSS_SELECTOR,
                                          f'#tblMessages > tbody > tr:nth-child({cnt}) > td:nth-child(5)')  # находим элемент по селектору
        next_button.click()  # нажимаем кнопку

        time.sleep(1.5)

        # Получаем список всех открытых окон/вкладок
        windows = driver.window_handles

        # Переключаемся на новое окно (последнее в списке)
        driver.switch_to.window(windows[1])

        time.sleep(2)

        l = driver.find_elements(By.TAG_NAME, "td")

        if "о признании гражданина банкротом и введении реализации имущества гражданина" in l[7].text:
            for i in range(len(l)):
                if l[i].text == "№ сообщения":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'№ сообщения:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Дата публикации":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Дата публикации:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "ФИО должника":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'ФИО должника:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Дата рождения":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Дата рождения:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Место рождения":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Место рождения:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Место жительства":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Место жительства:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "ИНН":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'ИНН:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "СНИЛС":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'СНИЛС:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Ранее имевшиеся ФИО":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Ранее имевшиеся ФИО:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "№ дела":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'№ дела:{l[i+1].text}\n')  # \n для перевода на новую строку
                elif l[i].text == "Арбитражный управляющий":
                    with open(f'people\\{folder_name}\\Информация.txt', 'a', encoding='utf-8') as file:
                        file.write(f'Арбитражный управляющий:{l[i+1].text}\n')  # \n для перевода на новую строку

            driver.close()
            time.sleep(1)
            driver.switch_to.window(windows[0])

            driver.get("https://old.bankrot.fedresurs.ru/BackOffice/ArbitrManager/PaymentOperationReport.aspx")
            time.sleep(1)
            next_button = driver.find_element(By.CSS_SELECTOR,"#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_ucDebtorPaymentOperationsReport_tdBankrupt > td:nth-child(2) > table > tbody > tr > td:nth-child(2) > img")
            next_button.click()

            time.sleep(2)

            driver.switch_to.frame(0)  # переключаемся на новое окно

            next_button = driver.find_element(By.CSS_SELECTOR,
                                              '#ctl00_cplhContent_InsolventList_radTs > div > ul > li.rtsLI.rtsLast > a > span > span > span')  # находим элемент по селектору
            next_button.click()  # нажимаем кнопку

            time.sleep(1)

            txt_input = driver.find_element(By.CSS_SELECTOR,
                                            '#ctl00_cplhContent_InsolventList_tbLastNameEgrip')  # # находим элемент по селектору
            txt_input.clear()  # отчищаем поле для ввода
            txt_input.send_keys(Last_name)  # вводим текст

            txt_input = driver.find_element(By.CSS_SELECTOR,
                                            '#ctl00_cplhContent_InsolventList_tbFirstNameEgrip')  # # находим элемент по селектору
            txt_input.clear()  # отчищаем поле для ввода
            txt_input.send_keys(Name)  # вводим текст

            txt_input = driver.find_element(By.CSS_SELECTOR,
                                            '#ctl00_cplhContent_InsolventList_tbMiddleNameEgrip')  # # находим элемент по селектору
            txt_input.clear()  # отчищаем поле для ввода
            txt_input.send_keys(Middle_name)  # вводим текст

            next_button = driver.find_element(By.CSS_SELECTOR,
                                              '#ctl00_cplhContent_InsolventList_btnSearchEgrip')  # находим элемент по селектору
            next_button.click()  # нажимаем кнопку

            time.sleep(2)

            next_button = driver.find_element(By.CSS_SELECTOR,
                                              '#resultTable > tbody > tr:nth-child(2) > td:nth-child(2)')  # находим элемент по селектору
            next_button.click()  # нажимаем кнопку

            driver.switch_to.default_content()  # переключаемся на основное окно

            txt_input = driver.find_element(By.CSS_SELECTOR,
                                            '#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_ucDebtorPaymentOperationsReport_dtpStartDate_radDatePicker_dateInput')  # # находим элемент по селектору
            txt_input.clear()  # отчищаем поле для ввода
            txt_input.send_keys(three_years_ago)  # вводим текст

            txt_input = driver.find_element(By.CSS_SELECTOR,
                                            '#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_ucDebtorPaymentOperationsReport_dtpEndDate_radDatePicker_dateInput')  # # находим элемент по селектору
            txt_input.clear()  # отчищаем поле для ввода
            txt_input.send_keys(current_date)  # вводим текст

            time.sleep(0.5)

            next_button = driver.find_element(By.CSS_SELECTOR,
                                              '#ctl00_ctl00_ctplhMain_CentralContentPlaceHolder_ucDebtorPaymentOperationsReport_btnCreateBankruptReport')  # находим элемент по селектору
            next_button.click()  # нажимаем кнопку

            # Используем вашу функцию для ожидания скачивания и получения пути к файлу
            downloaded_pdf_path = wait_for_download_complete(download_dir, timeout=60)

            if downloaded_pdf_path:
                print(f"PDF файл успешно скачан: {downloaded_pdf_path}")
                pdf_text = ""
                try:
                    with open(downloaded_pdf_path, 'rb') as pdf_file:
                        pdf_reader = PyPDF2.PdfReader(pdf_file)
                        for page in pdf_reader.pages:
                            pdf_text += page.extract_text() + "\n"

                    total_sum = None
                    for line in pdf_text.splitlines():
                        if line.strip().startswith("Сумма итого:"):
                            value_part = line.split(":")[1].strip()

                            # --- ИСПРАВЛЕНИЕ С ПОМОЩЬЮ РЕГУЛЯРНЫХ ВЫРАЖЕНИЙ ---
                            cleaned_sum = re.sub(r'\s+', ' ', value_part).replace(',', '.')

                            total_sum = cleaned_sum
                            break

                    if total_sum:
                        info_file_path = f'people\\{folder_name}\\Информация.txt'
                        with open(info_file_path, 'a', encoding='utf-8') as info_file:
                            info_file.write(f'Сумма итого:{total_sum}\n')
                        print(f"✅ Итоговая сумма '{total_sum}' добавлена в файл: {info_file_path}")
                    else:
                        print("⚠️ Предупреждение: не удалось найти строку 'Сумма итого:' в тексте PDF.")


                except Exception as pdf_error:
                    print(f"❌ Ошибка при чтении PDF файла: {pdf_error}")
                finally:
                    os.remove(downloaded_pdf_path)
                    print(f"Временный PDF файл '{os.path.basename(downloaded_pdf_path)}' удален.")
            else:
                print("❌ Ошибка: PDF файл не был скачан за отведенное время.")

            cnt = 0
        else:
            driver.close()
            time.sleep(1)
            driver.switch_to.window(windows[0])
            cnt += 1


except Exception as e:
    print(f"Ошибка: {e}")

simple_txt_to_json(f'people\\{folder_name}\\Информация.txt',f'people\\{folder_name}\\Информация.json')