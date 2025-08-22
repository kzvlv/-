import time
from selenium import webdriver
import selenium  # полностью импортируем библиотеку
from selenium.webdriver.common.by import By  # подключаем определенную функцию из библиотеки
import os
import json
from selenium.webdriver.common.action_chains import ActionChains


driver = webdriver.Chrome()
driver.get("https://bankruptcy.kommersant.ru/search/poisk_soobshcheniya_o_bankrotstve/")
time.sleep(3)

people_path = 'people'

# Получаем все элементы в папке
items = os.listdir(people_path)

# Ищем первую папку
for item in items:
    item_path = os.path.join(people_path, item)
    if os.path.isdir(item_path):
        folder_name = item
        break

# Чтение из файла
with open(f'people\\{folder_name}\\Информация.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

inn = data["ИНН"]


url = "https://bankruptcy.kommersant.ru/search/poisk_soobshcheniya_o_bankrotstve"
driver.get(url)
driver.maximize_window()
driver.refresh()
time.sleep(3)

input_field = driver.find_element(By.CSS_SELECTOR, '#search_inn > div > input')
input_field.clear()
input_field.send_keys("*" + inn + "*")
time.sleep(3)

search_button = driver.find_element(By.CSS_SELECTOR,
                                    'body > div.layout > div.col_group > div.col-left > div.main-search-form.container_Bankruptcy > div.search-sbk-block > div > div > div > input.hover.search-sbk__btn.one.active')
ActionChains(driver).move_to_element(search_button).pause(1).click().perform()
time.sleep(2)

kom = [[],[],[],[]]

try:
    cnt = 0
    while True:
        if "Стрижаков" in driver.find_element(By.CSS_SELECTOR,f"body > div.layout > div.col_group > div.col-left > div.left-main-content > div > div:nth-child(2) > div:nth-child({cnt + 1}) > div.page-content-company-information > div > div.mesagge-body > div > div:nth-child(2)").text:
            kom[0].append(driver.find_element(By.CSS_SELECTOR,f"body > div.layout > div.col_group > div.col-left > div.left-main-content > div > div:nth-child(2) > div:nth-child({cnt + 1}) > div.text > h2").text.split()[2])
            kom[1].append(driver.find_element(By.CSS_SELECTOR,f"body > div.layout > div.col_group > div.col-left > div.left-main-content > div > div:nth-child(2) > div:nth-child({cnt + 1}) > div.text > h2").text.split()[-1])
            kom[2].append(driver.find_element(By.CSS_SELECTOR,f"body > div.layout > div.col_group > div.col-left > div.left-main-content > div > div:nth-child(2) > div:nth-child({cnt + 1}) > div.text > h1").text.split()[0])
            kom[3].append(driver.find_element(By.CSS_SELECTOR,f"body > div.layout > div.col_group > div.col-left > div.left-main-content > div > div:nth-child(2) > div:nth-child({cnt + 1}) > div.text > h1").text.split()[-1])
        cnt += 1
except:
    pass

summary_kom = 0

driver.get("https://bankruptcy.kommersant.ru/index.php?payonline")

for i in range(len(kom[0])):
    driver.refresh()
    time.sleep(3)
    next_input = driver.find_element(By.CSS_SELECTOR, "#input_pay_query")
    next_input.clear()
    next_input.send_keys(kom[0][i])
    next_button = driver.find_element(By.CSS_SELECTOR,"#bt_pay_query")
    next_button.click()
    time.sleep(1)
    btw = driver.find_element(By.CSS_SELECTOR,"#pay_search_result > p.pay_search_bill_amount").text
    summary_kom += float(btw[btw.index(":")+2:btw.index("р")-1].replace(",",".").replace(" ",""))


# Чтение файла
with open(f'people\\{folder_name}\\Информация.json', 'r', encoding='utf-8') as file:
    debtor_data = json.load(file)

# Добавляем служебную информацию
debtor_data["Номер объявления Коммерсант"] = kom[0][0]
debtor_data["Страница"] = kom[1][0]
debtor_data["Газета"] = kom[2][0]
debtor_data["Дата"] = kom[3][0]
debtor_data["Сумма Коммерсант"] = str(summary_kom)
# Записываем обратно

with open(f'people\\{folder_name}\\Информация.json', 'w', encoding='utf-8') as file:
    json.dump(debtor_data, file, ensure_ascii=False, indent=4)