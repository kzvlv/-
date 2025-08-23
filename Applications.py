import os
import json
from pathlib import Path
import google.generativeai as genai
import time
import re
from PyPDF2 import PdfReader, PdfWriter
import concurrent.futures

# --- НАСТРОЙКИ ---
# Загрузка данных для прокси и API из файлов
try:
    with open('autorization\\proxy.txt', 'r', encoding='utf-8') as file:
        proxy = file.read().split(":")
        PROXY_ADDRESS, PROXY_PORT, PROXY_LOGIN, PROXY_PASSWORD = proxy
except FileNotFoundError:
    print("⚠️ Файл 'autorization\\proxy.txt' не найден. Прокси не будет использоваться.")
    PROXY_ADDRESS = None

try:
    with open('autorization\\API_GEMINI.txt', 'r', encoding='utf-8') as file:
        GOOGLE_API_KEY = file.read().strip()
except FileNotFoundError:
    print("❌ Критическая ошибка: Файл 'autorization\\API_GEMINI.txt' не найден.")
    GOOGLE_API_KEY = None


# --- КОНЕЦ НАСТРОЕК ---


def setup_environment():
    """Настраивает прокси и API-ключ."""
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
    else:
        print(f"❌ Ошибка: Внутри '{people_dir}' должна быть ровно одна папка.")
        return None


def split_pdf_chunks(file_path, chunk_size=50):
    """Разделяет PDF-файл на части для загрузки в API."""
    if not file_path.exists():
        print(f"❌ Исходный PDF файл не найден: {file_path}")
        return []

    print(f"🔪 Разделение файла '{file_path.name}' на части по {chunk_size} страниц...")
    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    chunk_paths = []
    temp_dir = file_path.parent / "temp_pdf_chunks_for_slicing"
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

    print(f"✅ Файл разделен на {len(chunk_paths)} частей для анализа.")
    return chunk_paths


def upload_file_with_retry(file_path, max_retries=3):
    """Загружает файл с повторными попытками."""
    for attempt in range(max_retries):
        try:
            print(f"  > Попытка {attempt + 1}/{max_retries}: Загрузка '{file_path.name}'...")
            uploaded_file = genai.upload_file(path=file_path)
            time.sleep(1)
            return uploaded_file
        except Exception as e:
            print(f"  > ❌ Ошибка при загрузке '{file_path.name}': {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return None


def sanitize_filename(name):
    """Очищает имя файла от недопустимых символов."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


def create_document_inventory_and_split(person_folder, model):
    """
    Создает опись документов с помощью AI и разрезает исходный PDF на отдельные файлы.
    """
    # --- 1. Определение путей ---
    person_name = person_folder.name
    # Обратите внимание на новый путь к файлу
    source_pdf_path = person_folder / "Материалы дела Анализ" / "Материалы дела (Общий).pdf"
    output_dir = person_folder / "Приложения"

    if not source_pdf_path.exists():
        print(f"❌ Не найден исходный файл для разделения: {source_pdf_path}")
        return

    # Создаем папку для результатов, если ее нет
    output_dir.mkdir(exist_ok=True)
    print(f"📂 Результаты будут сохранены в: {output_dir}")

    # --- 2. Подготовка и загрузка файлов в AI ---
    pdf_chunks = split_pdf_chunks(source_pdf_path)
    if not pdf_chunks:
        return

    uploaded_files = []
    temp_dir = source_pdf_path.parent / "temp_pdf_chunks_for_slicing"

    try:
        # Многопоточная загрузка
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_file = {executor.submit(upload_file_with_retry, chunk): chunk for chunk in pdf_chunks}
            for future in concurrent.futures.as_completed(future_to_file):
                uploaded_file = future.result()
                if uploaded_file:
                    uploaded_files.append(uploaded_file)

        if not uploaded_files:
            print("❌ Не удалось загрузить ни одного файла. Завершение работы.")
            return

        # --- 3. Формирование промпта и запрос к AI ---
        prompt = """
Проанализируй приложенные части документа.
Твоя задача - составить опись всех логических документов, содержащихся в файле, и указать их точные диапазоны страниц.

Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.

JSON должен быть списком (массивом) объектов. Каждый объект должен представлять один документ и содержать три ключа:
1. "document_name": Краткое и точное наименование документа (например, "Паспорт РФ", "Кредитный договор №123 от 01.01.2022").
2. "start_page": Номер ПЕРВОЙ страницы документа (как число).
3. "end_page": Номер ПОСЛЕДНЕЙ страницы документа (как число).

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:
1. Нумерация страниц должна быть сквозной и соответствовать нумерации в исходном PDF-файле.
2. Не пропускай документы.
3. Указывай точные номера страниц.
4. "document_name" должен быть удобным для использования в качестве имени файла.
5. Если документ состоит из одной страницы, "start_page" и "end_page" должны быть одинаковыми.

Пример корректного вывода:
[
  {
    "document_name": "Паспорт РФ должника",
    "start_page": 1,
    "end_page": 3
  },
  {
    "document_name": "СНИЛС",
    "start_page": 4,
    "end_page": 4
  },
  {
    "document_name": "Кредитный договор №123-АБВ от 02.02.2022",
    "start_page": 5,
    "end_page": 12
  }
]
"""
        print(f"🧠 Отправка запроса в Gemini для создания описи документов...")
        response = model.generate_content(uploaded_files + [prompt], request_options={"timeout": 1000})
        clean_json_str = re.sub(r'```json\s*|```', '', response.text).strip()

        # --- 4. Парсинг ответа и нарезка PDF ---
        document_inventory = json.loads(clean_json_str)

        print(f"✅ Получена опись из {len(document_inventory)} документов. Начинаю нарезку...")

        original_pdf_reader = PdfReader(source_pdf_path)
        total_pages_in_pdf = len(original_pdf_reader.pages)

        for i, doc_info in enumerate(document_inventory, 1):
            doc_name = doc_info.get("document_name", f"Документ_{i}")
            start_page = doc_info.get("start_page")
            end_page = doc_info.get("end_page")

            if start_page is None or end_page is None:
                print(f"  > ⚠️ Пропущен документ '{doc_name}' из-за отсутствия номеров страниц.")
                continue

            # Конвертируем в 0-индексацию для PyPDF2
            start_idx = start_page - 1
            end_idx = end_page - 1

            # Проверка корректности диапазона
            if not (0 <= start_idx <= end_idx < total_pages_in_pdf):
                print(
                    f"  > ⚠️ Пропущен '{doc_name}'. Неверный диапазон страниц: {start_page}-{end_page} (всего в файле {total_pages_in_pdf} стр.)")
                continue

            # Формируем имя файла
            safe_name = sanitize_filename(doc_name)
            output_filename = f"{i}. {safe_name}.pdf"
            output_filepath = output_dir / output_filename

            # Нарезка и сохранение
            try:
                writer = PdfWriter()
                for page_num in range(start_idx, end_idx + 1):
                    writer.add_page(original_pdf_reader.pages[page_num])

                with open(output_filepath, "wb") as f_out:
                    writer.write(f_out)
                print(f"  > ✅ Сохранен: '{output_filename}' (страницы {start_page}-{end_page})")
            except Exception as e:
                print(f"  > ❌ Ошибка при сохранении файла '{output_filename}': {e}")


    except json.JSONDecodeError:
        print("❌ Не удалось распознать JSON из ответа модели. Ответ был:")
        print(response.text)
    except Exception as e:
        print(f"❌ Произошла критическая ошибка: {e}")
    finally:
        # --- 5. Очистка ---
        print("🧹 Очистка временных файлов...")
        for chunk in pdf_chunks:
            try:
                os.remove(chunk)
            except OSError as e:
                print(f"  > Не удалось удалить временный файл {chunk}: {e}")
        try:
            os.rmdir(temp_dir)
        except OSError as e:
            # Папка может быть не пуста, если какой-то файл не удалился
            pass

        for uploaded_file in uploaded_files:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
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

    create_document_inventory_and_split(person_folder, model)


if __name__ == "__main__":
    main()
