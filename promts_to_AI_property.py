import os
import json
from pathlib import Path
import google.generativeai as genai
import time
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from PIL import Image
import fitz  # PyMuPDF
import concurrent.futures
from threading import Lock

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


def merge_and_split_documents(person_folder):
    """Объединяет все PDF и JPEG файлы и разбивает на части по 50 страниц."""
    materials_folder = person_folder / "Материалы дела"
    analysis_folder = person_folder / "Материалы дела Анализ"

    if not materials_folder.is_dir():
        print(f"❌ Папка 'Материалы дела' не найдена в {person_folder}")
        return False

    # Создаем папку для анализа
    analysis_folder.mkdir(exist_ok=True)

    # Находим все PDF и изображения
    pdf_files = list(materials_folder.glob("*.pdf"))
    image_files = list(materials_folder.glob("*.jpg")) + list(materials_folder.glob("*.jpeg"))

    if not pdf_files and not image_files:
        print("❌ Не найдено PDF или JPEG файлов в папке 'Материалы дела'")
        return False

    # Конвертируем изображения в PDF
    temp_pdfs = []
    for image_file in image_files:
        temp_pdf_path = analysis_folder / f"temp_{image_file.stem}.pdf"
        if convert_image_to_pdf(image_file, temp_pdf_path):
            temp_pdfs.append(temp_pdf_path)

    # Объединяем все PDF файлы
    merger = PdfMerger()

    # Добавляем оригинальные PDF
    for pdf_file in pdf_files:
        try:
            merger.append(str(pdf_file))
        except Exception as e:
            print(f"❌ Ошибка при добавлении {pdf_file}: {e}")

    # Добавляем конвертированные изображения
    for temp_pdf in temp_pdfs:
        try:
            merger.append(str(temp_pdf))
        except Exception as e:
            print(f"❌ Ошибка при добавлении временного PDF: {e}")

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
    for temp_pdf in temp_pdfs:
        try:
            temp_pdf.unlink()
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


def upload_file_wrapper(pdf_part):
    """Обертка для загрузки файла с обработкой ошибок."""
    try:
        print(f"  > Загрузка файла '{pdf_part.name}'...")
        uploaded_file = genai.upload_file(path=pdf_part)
        time.sleep(1)  # Небольшая пауза между запросами
        return uploaded_file
    except Exception as e:
        print(f"  > ❌ Ошибка при загрузке '{pdf_part.name}': {e}")
        return None


def analyze_property(person_folder, model):
    """Анализирует имущество человека."""
    analysis_folder = person_folder / "Материалы дела Анализ"
    person_name = person_folder.name

    if not analysis_folder.is_dir():
        print(f"❌ Папка анализа не найдена: {analysis_folder}")
        return None

    # Получаем все части материалов дела
    pdf_parts = sorted(analysis_folder.glob("Материалы дела *.pdf"))

    if not pdf_parts:
        print("❌ Не найдены части материалов дела для анализа")
        return None

    print(f"🔍 Анализ имущества для: {person_name}")

    uploaded_files = []
    try:
        # Многопоточная загрузка файлов (по 5 одновременно)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            # Запускаем загрузку всех файлов
            future_to_file = {executor.submit(upload_file_wrapper, pdf_part): pdf_part for pdf_part in pdf_parts}

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
            return None

        prompt_text = f"""
Есть ли согласно приложенным файлам у {person_name} зарегистрированное имущество? 
Отдели Движимое, Недвижимое, Денежные средства.
Также определи для каждого стоимость(в рублях!) определенную финансовым управляющим! 
Определи единственное жилье (для него стоимость не нужна! И к недвижимому имущество добавлять не нужно!)

ВАЖНО: Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.

Формат JSON:
{{
  "only_accommodation": "Единственное жилье или -",
  "immovable_property": "Недвижимое имущество через точку с запятой или -",
  "immovable_property_price": "Цены недвижимости через точку с запятой или -",
  "movable_property": "Движимое имущество через точку с запятой или -",
  "movable_property_price": "Цены движимости через точку с запятой или -",
  "cash_property": "Денежные средства через точку с запятой или -",
  "cash_property_price": "Суммы денежных средств через точку с запятой или -"
}}

ПРАВИЛА:
1. Для цен пиши без пробелов, для десятичных дробей вместо запятой используй точку! (например 7806.27)
2. Если несколько позиций в категории - перечисляй через точку с запятой, цены тоже через точку с запятой в том же порядке
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

        print("  > Анализ файлов...")
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

    finally:
        # Удаляем загруженные файлы
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

    # Шаг 1: Объединяем и разбиваем материалы дела
    print("📂 Объединение и разбивка материалов дела...")
    if not merge_and_split_documents(person_folder):
        print("❌ Не удалось обработать материалы дела")
        return

    # Шаг 2: Анализируем имущество
    print("\n🔍 Анализ имущества...")
    property_analysis = analyze_property(person_folder, model)

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


if __name__ == "__main__":
    main()