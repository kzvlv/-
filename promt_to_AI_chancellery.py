import os
import json
from pathlib import Path
import google.generativeai as genai
import time
import concurrent.futures
import re

with open('autorization\\proxy.txt', 'r', encoding='utf-8') as file:
    proxy = file.read().split(":")
    PROXY_ADDRESS = proxy[0]
    PROXY_PORT = proxy[1]
    PROXY_LOGIN = proxy[2]
    PROXY_PASSWORD = proxy[3]
with open('autorization\\API_GEMINI.txt', 'r', encoding='utf-8') as file:
    GOOGLE_API_KEY = file.read()


def setup_environment():
    """Настраивает прокси и API-ключ в правильном порядке."""
    try:
        if PROXY_ADDRESS:
            proxy_url = f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_ADDRESS}:{PROXY_PORT}"
            os.environ['HTTPS_PROXY'] = proxy_url
            os.environ['HTTP_PROXY'] = proxy_url
            print(f"🚀 Прокси установлен: {PROXY_ADDRESS}:{PROXY_PORT}")

        genai.configure(api_key=GOOGLE_API_KEY)
        print("✅ Конфигурация Google AI прошла успешно.")
        return True

    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False


def find_person_folder():
    """Находит единственную папку внутри директории 'People'."""
    people_dir = Path("People")
    if not people_dir.is_dir():
        print(f"❌ Ошибка: Директория '{people_dir}' не найдена.")
        return None

    subdirectories = [d for d in people_dir.iterdir() if d.is_dir()]
    if len(subdirectories) == 1:
        return subdirectories[0]
    else:
        print(f"❌ Ошибка: Внутри '{people_dir}' должна быть ровно одна папка.")
        return None


def upload_file_with_retry(file_path, max_retries=3):
    """Загружает файл с повторными попытками при ошибках."""
    for attempt in range(max_retries):
        try:
            print(f"  > Попытка {attempt + 1}/{max_retries}: Загрузка файла '{file_path.name}'...")
            uploaded_file = genai.upload_file(path=file_path)
            time.sleep(1)
            return uploaded_file
        except Exception as e:
            print(f"  > ❌ Ошибка при загрузке '{file_path.name}' (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Пауза перед повторной попыткой
    return None


def extract_amounts_from_text(text):
    """Извлекает суммы денег из текста."""
    # Ищем числа с десятичными дробями (формат: 123.45)
    amounts = re.findall(r'\b\d+\.\d{2}\b', text)
    # Ищем целые числа (формат: 123)
    amounts += re.findall(r'\b\d+\b', text)
    # Конвертируем в float
    return [float(amount) for amount in amounts if float(amount) > 0]


def analyze_stationery_expenses(person_folder, model):
    """Анализирует канцелярские расходы из JPG файлов с 'почт' в названии."""
    materials_folder = person_folder / "Материалы дела"
    person_name = person_folder.name

    if not materials_folder.is_dir():
        print(f"❌ Папка 'Материалы дела' не найдена в {person_folder}")
        return None

    # Находим все JPG файлы с 'почт' в названии (регистронезависимо)
    post_files = []
    for pattern in ["*почт*", "*Почт*", "*ПОЧТ*"]:
        post_files.extend(list(materials_folder.glob(f"{pattern}.jpg")))
        post_files.extend(list(materials_folder.glob(f"{pattern}.jpeg")))

    # Убираем дубликаты
    post_files = list(set(post_files))

    if not post_files:
        print("❌ Не найдено JPG файлов с 'почт' в названии")
        return {"sum chancellery": "0.00"}

    print(f"📸 Найдено файлов Почты России: {len(post_files)}")
    print(f"📊 Анализ почтовых расходов для: {person_name}")

    uploaded_files = []
    try:
        # Многопоточная загрузка файлов (по 3 одновременно)
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Запускаем загрузку всех файлов
            future_to_file = {executor.submit(upload_file_with_retry, post_file): post_file for post_file in post_files}

            # Собираем результаты
            for future in concurrent.futures.as_completed(future_to_file):
                post_file = future_to_file[future]
                try:
                    uploaded_file = future.result()
                    if uploaded_file:
                        uploaded_files.append(uploaded_file)
                        print(f"  > ✅ Успешно загружен: {post_file.name}")
                except Exception as e:
                    print(f"  > ❌ Ошибка при загрузке {post_file.name}: {e}")

        if not uploaded_files:
            print("❌ Не удалось загрузить ни одного файла")
            return {"sum chancellery": "0.00"}

        prompt_text = """
Проанализируй приложенные скриншоты/изображения. 
Найди информацию о почтовых расходах (канцелярских расходах). Эта информация берется только с сайта ПОЧТА РОССИИ. Найди именно этот скриншот. 

ВАЖНО: Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.

Формат JSON:
{
"amounts": ["список", "всех", "найденных", "сумм"]
}

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Указывай ТОЛЬКО те суммы, которые явно видны на скриншотах Почты России
2. Если информации о расходах нет - верни {"amounts": []}
3. НЕ придумывай суммы и не пытайся их вычислять на основе логики
4. Если сумма указана с копейками - сохраняй копейки
5. Для десятичных дробей используй точку вместо запятой
6. Убирай все пробелы в числах
7. НЕ СУММИРУЙ суммы самостоятельно! Просто верни все найденные числа
8. Вывод только JSON

Пример корректного вывода если найдены расходы:
{
"amounts": ["125.50", "300.00", "87.25"]
}

Пример если расходов не найдено:
{
"amounts": []
}
"""

        print("  > Анализ почтовых расходов...")
        response = model.generate_content(uploaded_files + [prompt_text], request_options={"timeout": 600})
        response_text = response.text.strip()

        # Очищаем ответ от возможного markdown форматирования
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '').replace('```', '').strip()
        elif response_text.startswith('```'):
            response_text = response_text.replace('```', '').strip()

        result = json.loads(response_text)
        amounts_list = result.get("amounts", [])

        # Суммируем все найденные суммы
        total = 0.0
        valid_amounts = []

        for amount_str in amounts_list:
            try:
                # Очищаем строку от пробелов и лишних символов
                clean_amount = amount_str.replace(' ', '').replace(',', '.')
                amount = float(clean_amount)
                if amount > 0:
                    total += amount
                    valid_amounts.append(amount)
            except (ValueError, TypeError):
                continue

        print(f"  > Найдено сумм: {len(valid_amounts)}")
        print(f"  > Общая сумма: {total:.2f}")

        # Формируем финальный результат
        final_result = {"sum chancellery": f"{total:.2f}"}

        # Сохраняем результат
        stationery_file = person_folder / "Канцелярские расходы.json"
        with open(stationery_file, "w", encoding="utf-8") as f:
            json.dump(final_result, f, ensure_ascii=False, indent=4)
        print(f"✅ Результат анализа канцелярских расходов сохранен: {stationery_file}")

        return final_result

    except Exception as e:
        print(f"❌ Ошибка при анализе канцелярских расходов: {e}")
        return {"sum chancellery": "0.00"}

    finally:
        # Удаляем загруженные файлы в конце
        for uploaded_file in uploaded_files:
            try:
                genai.delete_file(uploaded_file.name)
            except:
                pass


def main():
    if not setup_environment():
        return

    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    person_folder = find_person_folder()
    if not person_folder:
        return

    # Анализируем канцелярские расходы из JPG файлов с "почт" в названии
    print("📊 Анализ канцелярских расходов (Почта России)...")
    stationery_result = analyze_stationery_expenses(person_folder, model)

    if stationery_result:
        print("\n📊 Результаты анализа канцелярских расходов:")
        for key, value in stationery_result.items():
            print(f"  {key}: {value}")
    else:
        print("❌ Не удалось проанализировать канцелярские расходы")


if __name__ == "__main__":
    main()