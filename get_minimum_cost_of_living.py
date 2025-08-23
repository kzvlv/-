import os
import json
from pathlib import Path
import google.generativeai as genai
import time
import re
from PyPDF2 import PdfReader, PdfWriter
from datetime import datetime
import concurrent.futures

# --- НАСТРОЙКИ ---
# Загрузка данных для прокси и API из файлов
try:
    with open('autorization\\proxy.txt', 'r', encoding='utf-8') as file:
        proxy = file.read().split(":")
        PROXY_ADDRESS = proxy[0]
        PROXY_PORT = proxy[1]
        PROXY_LOGIN = proxy[2]
        PROXY_PASSWORD = proxy[3]
except FileNotFoundError:
    print("⚠️ Файл 'autorization\\proxy.txt' не найден. Прокси не будет использоваться.")
    PROXY_ADDRESS = None

try:
    with open('autorization\\API_GEMINI.txt', 'r', encoding='utf-8') as file:
        GOOGLE_API_KEY = file.read().strip()
except FileNotFoundError:
    print("❌ Критическая ошибка: Файл 'autorization\\API_GEMINI.txt' не найден. Укажите ваш API ключ.")
    GOOGLE_API_KEY = None


# --- КОНЕЦ НАСТРОЕК ---


def setup_environment():
    """Настраивает прокси и API-ключ в правильном порядке."""
    if not GOOGLE_API_KEY:
        print("❌ API ключ Google не найден. Завершение работы.")
        return False
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
        print(f"📂 Найдена папка для анализа: {subdirectories[0].name}")
        return subdirectories[0]
    elif len(subdirectories) > 1:
        print(f"❌ Ошибка: Внутри '{people_dir}' найдено несколько папок. Оставьте только одну.")
        return None
    else:
        print(f"❌ Ошибка: Внутри '{people_dir}' папки не найдены.")
        return None


def split_pdf(file_path, chunk_size=50):
    """Разделяет PDF-файл на части по chunk_size страниц."""
    if not file_path.exists():
        print(f"❌ Файл для анализа не найден: {file_path}")
        return []

    print(f"🔪 Разделение файла '{file_path.name}' на части по {chunk_size} страниц...")
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    chunk_paths = []
    temp_dir = file_path.parent / "temp_pdf_chunks"
    temp_dir.mkdir(exist_ok=True)

    for i in range(0, total_pages, chunk_size):
        writer = PdfWriter()
        end_page = min(i + chunk_size, total_pages)
        for page_num in range(i, end_page):
            writer.add_page(reader.pages[page_num])

        chunk_path = temp_dir / f"part_{i // chunk_size + 1}.pdf"
        with open(chunk_path, "wb") as f:
            writer.write(f)
        chunk_paths.append(chunk_path)

    print(f"✅ Файл разделен на {len(chunk_paths)} частей.")
    return chunk_paths


def upload_file_with_retry(file_path, max_retries=3):
    """Загружает файл с повторными попытками при ошибках."""
    for attempt in range(max_retries):
        try:
            print(f"  > Попытка {attempt + 1}/{max_retries}: Загрузка файла '{file_path.name}'...")
            uploaded_file = genai.upload_file(path=file_path)
            time.sleep(1)  # Задержка для избежания превышения лимитов API
            return uploaded_file
        except Exception as e:
            print(f"  > ❌ Ошибка при загрузке '{file_path.name}' (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Экспоненциальная задержка
    return None


def analyze_subsistence_minimum(person_folder, model):
    """
    Анализирует доходы, извлекает дату решения, формирует запрос и получает данные о прожиточном минимуме.
    """
    person_name = person_folder.name
    income_file = person_folder / "Доходы.json"
    info_file = person_folder / "Информация.json"  # <-- НОВОЕ: Путь к файлу с информацией
    analysis_pdf = person_folder / "Материалы дела Анализ\\Материалы дела (Общий).pdf"
    output_file = person_folder / "Прожиточный минимум.json"

    # --- НОВЫЙ БЛОК: Извлечение даты решения ---
    decision_date = None
    if not info_file.exists():
        print(f"⚠️  Файл '{info_file.name}' не найден. Невозможно получить 'Дату решения'. Запрос не будет выполнен.")
        return
    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            info_data = json.load(f)
            decision_date = info_data.get("Дата решения")
            if not decision_date:
                print(f"❌ В файле '{info_file.name}' не найдено поле 'Дата решения'. Запрос не будет выполнен.")
                return
            print(f"✅ Найдена дата решения: {decision_date}")
    except (json.JSONDecodeError, Exception) as e:
        print(f"❌ Ошибка чтения файла '{info_file.name}': {e}. Запрос не будет выполнен.")
        return
    # --- КОНЕЦ НОВОГО БЛОКА ---

    if not income_file.exists():
        print(f"❌ Файл '{income_file.name}' не найден. Анализ невозможен.")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        print(f"ℹ️ Создан пустой файл: {output_file.name}")
        return

    try:
        with open(income_file, 'r', encoding='utf-8') as f:
            income_data = json.load(f)
    except json.JSONDecodeError:
        print(f"❌ Ошибка чтения JSON из файла '{income_file.name}'.")
        return

    source_of_receipt = income_data.get("source_of_receipt", "")
    current_date = datetime.now().strftime("%d.%m.%Y")

    prompt = ""
    # Теперь decision_date используется в обоих промптах
    if "зарплата" in source_of_receipt.lower():
        print("ℹ️ Обнаружен доход 'зарплата'. Формируется запрос по региону.")
        prompt = f"""
Проанализируй приложенные документы.
Какой размер прожиточного минимума трудоспособного гражданина ({person_name}) по его Региону проживания в период с {decision_date} по {current_date}?
Нужно учесть и детей (если информация о них есть в документах), на одного ребенка приходится прожиточный минимум на ребенка по тому же Региону проживания.

Верни ОБЩУЮ СУММУ за всех людей (взрослый + все дети) за ВЕСЬ УКАЗАННЫЙ ПЕРИОД.Считай не в "голове", а с помощью python-кода!

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Ответ должен быть СТРОГО в формате JSON. Никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.
2. Сумма должна быть за весь период, а не за один месяц.
3. Верни число без пробелов. Для десятичной дроби используй точку вместо запятой.
4. На детей и на {person_name} прожиточный минимум рассчитывается по их региону проживания.
5. Если информации о детях или регионе нет, рассчитай только для {person_name} по среднероссийскому минимуму.

Формат JSON:
{{
"minimum": "СУММА"(ЗА ВСЕХ ЛЮДЕЙ!)
}}

Пример вывода:
{{
"minimum": "420514.40"
}}
"""
    elif source_of_receipt:
        print("ℹ️ Обнаружен другой источник дохода. Формируется смешанный запрос (среднероссийский + регион).")
        prompt = f"""
Проанализируй приложенные документы.
Какой среднероссийский размер прожиточного минимума для трудоспособного гражданина ({person_name}) в период с {decision_date} по {current_date}?
Также нужно учесть и детей (если информация о них есть в документах). На одного ребенка приходится прожиточный минимум на ребенка по их Региону проживания.

Верни ОБЩУЮ СУММУ за всех людей (взрослый + все дети) за ВЕСЬ УКАЗАННЫЙ ПЕРИОД.Считай не в "голове", а с помощью python-кода!

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Ответ должен быть СТРОГО в формате JSON. Никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.
2. Сумма должна быть за весь период, а не за один месяц.
3. Верни число без пробелов. Для десятичной дроби используй точку вместо запятой.
4. На детей прожиточный минимум рассчитывается по их региону, а на {person_name} — СРЕДНЕРОССИЙСКИЙ.
5. Если информации о детях или регионе нет, рассчитай только для {person_name} по среднероссийскому минимуму.

Формат JSON:
{{
"minimum": "СУММА"(ЗА ВСЕХ ЛЮДЕЙ!)
}}

Пример вывода:
{{
"minimum": "420514.40"
}}
"""
    else:
        print("ℹ️ Поле 'source_of_receipt' пустое. Запрос к AI не выполняется.")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({}, f)
        print(f"✅ Создан пустой файл: {output_file.name}")
        return

    # --- Работа с файлами и API (этот блок без изменений) ---
    pdf_chunks = split_pdf(analysis_pdf)
    if not pdf_chunks:
        return

    uploaded_files = []
    temp_dir = analysis_pdf.parent / "temp_pdf_chunks"

    try:
        # Многопоточная загрузка файлов
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_file = {executor.submit(upload_file_with_retry, chunk): chunk for chunk in pdf_chunks}
            for future in concurrent.futures.as_completed(future_to_file):
                uploaded_file = future.result()
                if uploaded_file:
                    uploaded_files.append(uploaded_file)

        if len(uploaded_files) != len(pdf_chunks):
            print("❌ Не все части файла удалось загрузить. Анализ может быть неполным.")

        if not uploaded_files:
            print("❌ Не удалось загрузить ни одного файла. Завершение работы.")
            return

        print(f"🧠 Отправка запроса в Gemini ({len(uploaded_files)} файлов)...")
        response = model.generate_content(uploaded_files + [prompt], request_options={"timeout": 600})
        response_text = response.text.strip()

        # Очистка ответа от markdown
        clean_json_str = re.sub(r'```json\s*|```', '', response_text).strip()

        # Парсинг и сохранение результата
        result_data = json.loads(clean_json_str)

        # Валидация и форматирование числа
        if "minimum" in result_data:
            try:
                min_value = float(str(result_data["minimum"]).replace(" ", ""))
                result_data["minimum"] = f"{min_value:.2f}"
            except (ValueError, TypeError):
                print(f"⚠️ Не удалось преобразовать значение 'minimum' в число: {result_data['minimum']}")
                result_data["minimum"] = "0.00"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=4)
        print(f"✅ Результат анализа сохранен: {output_file}")

    except Exception as e:
        print(f"❌ Произошла ошибка во время анализа: {e}")
    finally:
        # Удаление временных файлов и загруженных файлов
        print("🧹 Очистка временных файлов...")
        for chunk in pdf_chunks:
            try:
                os.remove(chunk)
            except OSError as e:
                print(f"  > Не удалось удалить временный файл {chunk}: {e}")
        try:
            os.rmdir(temp_dir)
        except OSError as e:
            print(f"  > Не удалось удалить временную папку {temp_dir}: {e}")

        for uploaded_file in uploaded_files:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e:
                # Ошибки при удалении не критичны
                pass
        print("✅ Очистка завершена.")


def main():
    """Основная функция для запуска скрипта."""
    if not setup_environment():
        return

    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    person_folder = find_person_folder()
    if not person_folder:
        return

    analyze_subsistence_minimum(person_folder, model)


if __name__ == "__main__":
    main()
