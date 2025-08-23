import os
import json
from pathlib import Path
import google.generativeai as genai
import time
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from PIL import Image
import fitz  # PyMuPDF
import concurrent.futures
from datetime import datetime
import re
import threading

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


def convert_image_to_pdf(image_path, output_pdf_path):
    """Конвертирует изображение в PDF."""
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output_pdf_path, "PDF", resolution=100.0)
        return True
    except Exception as e:
        print(f"❌ Ошибка конвертации {image_path}: {e}")
        return False


def upload_file_with_retry(pdf_part, max_retries=3):
    """Загружает файл с повторными попытками при ошибках."""
    for attempt in range(max_retries):
        try:
            print(f"  > Попытка {attempt + 1}/{max_retries}: Загрузка файла '{pdf_part.name}'...")
            uploaded_file = genai.upload_file(path=pdf_part)
            time.sleep(1)
            return uploaded_file
        except Exception as e:
            print(f"  > ❌ Ошибка при загрузке '{pdf_part.name}' (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Пауза перед повторной попыткой
    return None


def extract_relevant_pages_parallel(person_folder, model):
    """Извлекает релевантные страницы из документов с 'др' в названии (многопоточный)."""
    materials_folder = person_folder / "Материалы дела"
    person_name = person_folder.name

    # Находим файлы с 'др' в названии (регистронезависимо)
    dr_files = []
    for pattern in ["*др*", "*Др*", "*ДР*", "*другие*", "*Другие*", "*ДРУГИЕ*"]:
        dr_files.extend(list(materials_folder.glob(f"{pattern}.pdf")))
        dr_files.extend(list(materials_folder.glob(f"{pattern}.jpg")))
        dr_files.extend(list(materials_folder.glob(f"{pattern}.jpeg")))

    # Убираем дубликаты
    dr_files = list(set(dr_files))

    if not dr_files:
        print("📄 Файлы с 'др' в названии не найдены")
        return []

    print(f"🔍 Найдены файлы с 'др': {[f.name for f in dr_files]}")

    # Подготовка файлов для многопоточной обработки
    files_to_process = []
    for dr_file in dr_files:
        # Конвертируем изображения в PDF если нужно
        if dr_file.suffix.lower() in ['.jpg', '.jpeg']:
            temp_pdf = materials_folder / f"temp_{dr_file.stem}.pdf"
            if convert_image_to_pdf(dr_file, temp_pdf):
                files_to_process.append(temp_pdf)
        else:
            files_to_process.append(dr_file)

    # Многопоточная обработка файлов
    relevant_pages_files = []
    lock = threading.Lock()

    def process_file_wrapper(file_path):
        nonlocal relevant_pages_files
        try:
            # Проверяем количество страниц
            with open(file_path, 'rb') as f:
                reader = PdfReader(f)
                total_pages = len(reader.pages)
                print(f"  📊 Файл {file_path.name}: {total_pages} страниц")

                # Если больше 50 страниц, разбиваем на части
                if total_pages > 50:
                    print(f"  ✂️  Файл {file_path.name} слишком большой, разбиваем на части...")
                    parts = split_pdf_into_parts(file_path, 50)
                    for part_file in parts:
                        result = process_dr_file_with_retry(part_file, person_name, model)
                        with lock:
                            relevant_pages_files.extend(result)
                        # Удаляем временный файл части
                        try:
                            part_file.unlink()
                        except:
                            pass
                else:
                    result = process_dr_file_with_retry(file_path, person_name, model)
                    with lock:
                        relevant_pages_files.extend(result)

        except Exception as e:
            print(f"  ❌ Ошибка при обработке файла {file_path.name}: {e}")

        # Удаляем временный PDF если это было изображение
        if file_path.name.startswith("temp_"):
            try:
                file_path.unlink()
            except:
                pass

    # Запускаем многопоточную обработку
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        executor.map(process_file_wrapper, files_to_process)

    return relevant_pages_files


def process_dr_file_with_retry(pdf_file, person_name, model, max_retries=3):
    """Обрабатывает один файл с 'др' с повторными попытками."""
    for attempt in range(max_retries):
        try:
            return process_dr_file(pdf_file, person_name, model)
        except Exception as e:
            print(f"  ❌ Ошибка при обработке файла {pdf_file.name} (попытка {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return []


def process_dr_file(pdf_file, person_name, model):
    """Обрабатывает один файл с 'др' и возвращает релевантные страницы."""
    try:
        print(f"  📤 Загрузка файла для анализа: {pdf_file.name}")
        uploaded_file = upload_file_with_retry(pdf_file)
        if not uploaded_file:
            return []

        prompt_text = f"""
Проанализируй PDF-документ. В документе содержится информация о разных людях.
Найди ВСЕ страницы, которые относятся к человеку с ФИО: {person_name}

ВАЖНО: Верни ответ СТРОГО в формате JSON. Только чистый JSON без каких-либо пояснений.

Формат ответа:
{{
  "relevant_pages": [номера_страниц_через_запятую]
}}

Например, если страницы 5, 8 и 12 относятся к {person_name}:
{{
  "relevant_pages": [5, 8, 12]
}}

Если ни одна страница не относится к {person_name}, верни:
{{
  "relevant_pages": []
}}

Нумерация страниц начинается с 1!
"""

        response = model.generate_content([uploaded_file, prompt_text], request_options={"timeout": 300})
        response_text = response.text.strip().replace("```json", "").replace("```", "").strip()

        result = json.loads(response_text)
        relevant_pages = result.get("relevant_pages", [])

        print(f"  ✅ Найдено релевантных страниц: {len(relevant_pages)}")

        # Извлекаем релевантные страницы
        extracted_pages = extract_pages_from_pdf(pdf_file, relevant_pages, person_name)

        # Удаляем загруженный файл
        try:
            genai.delete_file(uploaded_file.name)
        except:
            pass

        return extracted_pages

    except Exception as e:
        print(f"  ❌ Ошибка при анализе файла {pdf_file.name}: {e}")
        return []


def split_pdf_into_parts(pdf_path, pages_per_part):
    """Разбивает PDF на части по указанному количеству страниц."""
    parts = []
    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            total_pages = len(reader.pages)

            part_number = 1
            for start_page in range(0, total_pages, pages_per_part):
                end_page = min(start_page + pages_per_part, total_pages)

                writer = PdfWriter()
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])

                part_filename = pdf_path.parent / f"{pdf_path.stem}_part{part_number}.pdf"
                with open(part_filename, 'wb') as output_file:
                    writer.write(output_file)

                parts.append(part_filename)
                part_number += 1

        return parts
    except Exception as e:
        print(f"❌ Ошибка при разбивке PDF: {e}")
        return []


def extract_pages_from_pdf(pdf_path, page_numbers, person_name):
    """Извлекает указанные страницы из PDF и возвращает список путей к извлеченным файлам."""
    if not page_numbers:
        # Если страницы не релевантны, удаляем файл
        try:
            pdf_path.unlink()
            print(f"  🗑️  Удален нерелевантный файл: {pdf_path.name}")
        except:
            pass
        return []

    try:
        with open(pdf_path, 'rb') as file:
            reader = PdfReader(file)
            writer = PdfWriter()

            for page_num in page_numbers:
                # Нумерация страниц в PyPDF2 начинается с 0
                if 0 <= page_num - 1 < len(reader.pages):
                    writer.add_page(reader.pages[page_num - 1])

            if len(writer.pages) > 0:
                output_filename = pdf_path.parent / f"{person_name}_релевантные_{pdf_path.stem}.pdf"
                with open(output_filename, 'wb') as output_file:
                    writer.write(output_file)

                print(f"  💾 Сохранено {len(writer.pages)} релевантных страниц в: {output_filename.name}")
                return [output_filename]

        return []
    except Exception as e:
        print(f"  ❌ Ошибка при извлечении страниц: {e}")
        return []


def merge_all_documents(person_folder, relevant_pages_files):
    """Объединяет все документы, включая релевантные страницы из 'др' файлов."""
    materials_folder = person_folder / "Материалы дела"
    analysis_folder = person_folder / "Материалы дела Анализ"

    # Создаем папку для анализа
    analysis_folder.mkdir(exist_ok=True)

    # Находим все PDF и изображения (кроме тех, что уже обработаны как 'др')
    all_files = []

    # Добавляем релевантные страницы из 'др' файлов
    all_files.extend(relevant_pages_files)

    # Добавляем остальные файлы (без 'др' в названии)
    for pattern in ["*.pdf", "*.jpg", "*.jpeg"]:
        for file_path in materials_folder.glob(pattern):
            # Пропускаем файлы с 'др' в названии, так как мы их уже обработали
            filename_lower = file_path.name.lower()
            if not any(keyword in filename_lower for keyword in ['др', 'другие']):
                all_files.append(file_path)

    if not all_files:
        print("❌ Не найдено файлов для обработки")
        return False

    # Конвертируем изображения в PDF
    pdf_files = []
    for file_path in all_files:
        if file_path.suffix.lower() in ['.jpg', '.jpeg']:
            temp_pdf_path = analysis_folder / f"temp_{file_path.stem}.pdf"
            if convert_image_to_pdf(file_path, temp_pdf_path):
                pdf_files.append(temp_pdf_path)
        else:
            pdf_files.append(file_path)

    # Объединяем все PDF файлы
    merger = PdfMerger()

    for pdf_file in pdf_files:
        try:
            merger.append(str(pdf_file))
        except Exception as e:
            print(f"❌ Ошибка при добавлении {pdf_file}: {e}")

    # Сохраняем объединенный PDF
    merged_pdf_path = analysis_folder / "Материалы дела.pdf"
    try:
        merger.write(str(merged_pdf_path))
        merger.close()
        print(f"✅ Объединенный PDF создан: {merged_pdf_path}")
    except Exception as e:
        print(f"❌ Ошибка при сохранении объединенного PDF: {e}")
        return False

    # Удаляем временные PDF файлы
    for pdf_file in pdf_files:
        if pdf_file.name.startswith("temp_"):
            try:
                pdf_file.unlink()
            except:
                pass

    # Разбиваем на части по 50 страниц
    try:
        with open(merged_pdf_path, 'rb') as file:
            reader = PdfReader(file)
            total_pages = len(reader.pages)

            part_number = 1
            for start_page in range(0, total_pages, 50):
                end_page = min(start_page + 50, total_pages)

                writer = PdfWriter()
                for page_num in range(start_page, end_page):
                    writer.add_page(reader.pages[page_num])

                part_filename = analysis_folder / f"Материалы дела {part_number}.pdf"
                with open(part_filename, 'wb') as output_file:
                    writer.write(output_file)

                print(f"✅ Создана часть {part_number}: {end_page - start_page} страниц")
                part_number += 1

        print(f"✅ Всего создано {part_number - 1} частей")
        return True

    except Exception as e:
        print(f"❌ Ошибка при разбивке PDF: {e}")
        return False


def get_decision_date(person_folder):
    """Получает дату решения из файла Информация.json."""
    info_file = person_folder / "Информация.json"
    if not info_file.exists():
        print(f"❌ Файл Информация.json не найден в {person_folder}")
        return None

    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            info_data = json.load(f)
            decision_date = info_data.get("Дата решения")
            if decision_date:
                print(f"✅ Дата решения найдена: {decision_date}")
                return decision_date
            else:
                print("❌ Поле 'Дата решения' не найдено в файле")
                return None
    except Exception as e:
        print(f"❌ Ошибка при чтении Информация.json: {e}")
        return None


def analyze_property(person_folder, model, uploaded_files):
    """Анализирует имущество человека."""
    person_name = person_folder.name

    print(f"🔍 Анализ имущества для: {person_name}")

    try:
        prompt_text = f"""
Есть ли согласно приложенным файлам у {person_name} зарегистрированное имущество? 
Отдели Движимое, Недвижимое, Денежные средства(Безналичные)! 
Также определи для каждого стоимость(в рублях!) определенную финансовым управляющим! 
Определи единственное жилье (для него стоимость не нужна! И к недвижимому имущество добавлять не нужно!)
Если есть определенная позиция, то у нее обязательно должна быть стоимость, определенная Арбитражным управляющим!

ВАЖНО: Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.

Формат JSON:
{{
  "only_accommodation": "Единственное жилье или -",
  "immovable_property": "Недвижимое имущество или -",
  "immovable_property_price": "Цены недвижимости через запятую или -",
  "movable_property": "Движимое имущество или -",
  "movable_property_price": "Цены движимости через запятую или -",
  "cash_property": "Денежные средства или -",
  "cash_property_price": "Суммы денежных средств через запятую или -"
}}

ПРАВИЛА:
1. Для цен пиши без пробелов, для десятичных дробей вместо запятой используй точку! (например 7806.27)
2. Если несколько позиций в категории - перечисляй через запятую, цены тоже через запятую в том же порядке
3. Если какой-то позиции нет, оставляй '-' (и для суммы тоже!)
4. Для единственного жилья указывай только описание, без цены
5. Будь внимателен к деталям в документах!

пример вывода:
{{
  "only_accommodation": "Квартира по адресу г. Воронеж, ул. Южно-Моравская, д. 12, кв. 14.",
  "immovable_property": "Частный дом по адресу г. Донец, ул. Варшваская д. 16",
  "immovable_property_price": "1300000",
  "movable_property": "Автомобиль Mazda 1998, Автомобиль Kia Rio 2016",
  "movable_property_price": "350000, 1200000",
  "cash_property": "-",
  "cash_property_price": "-"
}}
"""

        print("  > Анализ имущества...")
        response = model.generate_content(uploaded_files + [prompt_text], request_options={"timeout": 600})
        response_text = response.text.strip()

        # Очищаем ответ от возможного markdown форматирования
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '').replace('```', '').strip()
        elif response_text.startswith('```'):
            response_text = response_text.replace('```', '').strip()

        return json.loads(response_text)

    except Exception as e:
        print(f"❌ Ошибка при анализе имущества: {e}")
        return None


def analyze_income(person_folder, model, uploaded_files):
    """Анализирует доходы человека."""
    person_name = person_folder.name
    decision_date = get_decision_date(person_folder)

    if not decision_date:
        print("❌ Не удалось получить дату решения для анализа доходов")
        return None

    current_date = datetime.now().strftime("%d.%m.%Y")

    print(f"💰 Анализ доходов для: {person_name} (период: {decision_date} - {current_date})")

    try:
        prompt_text = f"""
Анализируй ТОЛЬКО фактические данные из приложенных документов. НЕ ПРИДУМЫВАЙ и НЕ ГЕНЕРИРУЙ данные!
Есть ли согласно приложенным файлам у {person_name} доходы за период с {decision_date} по {current_date}?
Мне нужно будет составить таблицу. Твоя задача написать все даты поступлений, источник поступления(Либо зарплата, либо пенсия, других вариантов нет), и размер поступления. Также нужно высчитать Итоговую сумму доходов. Не считай в "голове", для подсчета используй python-код.
Перечисления всех значений производится через точку с запятой!


ВАЖНО: Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.

Формат JSON:
{{
  "date of receipt": "даты через точку с запятой",
  "source of receipt": "источники через точку с запятой",
  "amount of the receipt": "суммы через точку с запятой",
  "total": "общая сумма"
}}

Если дохода не было вообще верни пустой json:
{{}}


КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Указывай ТОЛЬКО те доходы, которые явно указаны в документах
2. Если в документах нет информации о доходах - верни пустой JSON {{}}
3. НЕ придумывай даты, суммы или источники дохода
4. Если информация частичная или неполная - указывай только то, что есть в документах
5. Документы могут содержать информацию о разных периодах - учитывай только указанный период
6. В числах убирай пробелы, для десятичных дробей используй точку вместо запятой!
7. Источник может быть только "зарплата" или "пенсия"
8. Для подсчета общей суммы используй python-код, не считай вручную
9. Вывод только JSON
10. Обрати внимание, что могут попасться дубликаты(абсолютно одинаковые документы и сведения). Постарайся учти это и не прописывать дубликаты дважды! 
11. НЕСКОЛЬКИХ ДОХОДОВ ОТ ОДНОЙ ДАТЫ БЫТЬ НЕ МОЖЕТ!

Источники дохода могут быть только:
- зарплата (только если явно указано как заработная плата)
- пенсия (только если явно указано как пенсия)

пример вывода:
{{
  "date of receipt": "28.02.2025; 31.03.2025",
  "source of receipt": "зарплата; зарплата",
  "amount of the receipt": "31126.44; 33412.22",
  "total": "64538.66"
}}
"""

        print("  > Анализ доходов...")
        response = model.generate_content(uploaded_files + [prompt_text], request_options={"timeout": 600})
        response_text = response.text.strip()

        # Очищаем ответ от возможного markdown форматирования
        if response_text.startswith('```json'):
            response_text = response_text.replace('```json', '').replace('```', '').strip()
        elif response_text.startswith('```'):
            response_text = response_text.replace('```', '').strip()

        # Если ответ пустой или содержит только {}, возвращаем пустой dict
        if response_text.strip() in ['', '{}', '{{}}']:
            print("  💡 Доходы не обнаружены в документах")
            return {}

        result = json.loads(response_text)

        # Дополнительная проверка - если даты явно выглядят как выдуманные
        dates = result.get("date of receipt", "").split(";")
        if len(dates) > 12:  # Если больше 12 записей - подозрительно много
            print("  ⚠️  Обнаружено подозрительно много записей о доходах")
            print("  ⚠️  Вероятно, нейросеть сгенерировала данные вместо анализа")
            return {}

        return result

    except Exception as e:
        print(f"❌ Ошибка при анализе доходов: {e}")
        return None


def main():
    if not setup_environment():
        return

    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    person_folder = find_person_folder()
    if not person_folder:
        return

    person_name = person_folder.name

    # Шаг 1: Предварительная обработка файлов с 'др' в названии (многопоточная)
    print("🔍 Поиск и обработка файлов с 'др' в названии...")
    relevant_pages_files = extract_relevant_pages_parallel(person_folder, model)

    # Шаг 2: Объединяем все документы (включая релевантные страницы из 'др' файлов)
    print("\n📂 Объединение всех документов...")
    if not merge_all_documents(person_folder, relevant_pages_files):
        print("❌ Не удалось обработать материалы дела")
        return

    analysis_folder = person_folder / "Материалы дела Анализ"
    pdf_parts = sorted(analysis_folder.glob("Материалы дела *.pdf"))

    if not pdf_parts:
        print("❌ Не найдены части материалов дела для анализа")
        return

    uploaded_files = []
    try:
        # Многопоточная загрузка файлов (по 5 одновременно)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Запускаем загрузку всех файлов
            future_to_file = {executor.submit(upload_file_with_retry, pdf_part): pdf_part for pdf_part in pdf_parts}

            # Собираем результаты
            for future in concurrent.futures.as_completed(future_to_file):
                pdf_part = future_to_file[future]
                try:
                    uploaded_file = future.result()
                    if uploaded_file:
                        uploaded_files.append(uploaded_file)
                        print(f"  > ✅ Успешно загружен: {pdf_part.name}")
                except Exception as e:
                    print(f"  > ❌ Ошибка при загрузке {pdf_part.name}: {e}")

        if not uploaded_files:
            print("❌ Не удалось загрузить ни одного файла")
            return

        # Шаг 3: Анализируем имущество
        print("\n🔍 Анализ имущества...")
        property_analysis = analyze_property(person_folder, model, uploaded_files)

        if property_analysis and isinstance(property_analysis, dict):
            # Сохраняем результат
            property_file = person_folder / "Имущество.json"
            with open(property_file, "w", encoding="utf-8") as f:
                json.dump(property_analysis, f, ensure_ascii=False, indent=4)
            print(f"✅ Результат анализа имущества сохранен: {property_file}")

            # Выводим краткие результаты
            print("\n📊 Результаты анализа имущества:")
            for key, value in property_analysis.items():
                print(f"  {key}: {value}")
        else:
            print("❌ Не удалось проанализировать имущество")

        # Шаг 4: Анализируем доходы
        print("\n💰 Анализ доходов...")
        income_analysis = analyze_income(person_folder, model, uploaded_files)

        if income_analysis is not None:
            # Сохраняем результат
            income_file = person_folder / "Доходы.json"
            with open(income_file, "w", encoding="utf-8") as f:
                json.dump(income_analysis, f, ensure_ascii=False, indent=4)
            print(f"✅ Результат анализа доходов сохранен: {income_file}")

            if income_analysis:
                print("\n📊 Результаты анализа доходов:")
                for key, value in income_analysis.items():
                    print(f"  {key}: {value}")

                # Проверяем на подозрительное количество записей
                dates = income_analysis.get("date of receipt", "").split(";")
                if len(dates) > 12:
                    print("  🚨 ВНИМАНИЕ: Обнаружено подозрительно много записей о доходах!")
                    print("  🚨 Возможно, нейросеть сгенерировала данные вместо анализа документов")
                    print("  🚨 Рекомендуем проверить результат вручную")
            else:
                print("  💡 Доходы не обнаружены")
        else:
            print("❌ Не удалось проанализировать доходы")

    except Exception as e:
        print(f"❌ Общая ошибка: {e}")

    finally:
        # Удаляем загруженные файлы в конце
        for uploaded_file in uploaded_files:
            try:
                genai.delete_file(uploaded_file.name)
            except:
                pass


if __name__ == "__main__":
    main()