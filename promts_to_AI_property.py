import os
import json
from pathlib import Path
import google.generativeai as genai
import time
from PyPDF2 import PdfMerger, PdfReader, PdfWriter
from PIL import Image
import concurrent.futures
from datetime import datetime
import re
import threading
import tkinter as tk
from tkinter import filedialog

# --- БЛОК АВТОРИЗАЦИИ ---
try:
    with open('autorization\\proxy.txt', 'r', encoding='utf-8') as file:
        proxy = file.read().split(":")
        PROXY_ADDRESS, PROXY_PORT, PROXY_LOGIN, PROXY_PASSWORD = proxy
except FileNotFoundError:
    PROXY_ADDRESS = None
    print("⚠️  Файл с прокси не найден, работаем без него.")

with open('autorization\\API_GEMINI.txt', 'r', encoding='utf-8') as file:
    GOOGLE_API_KEY = file.read()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_decision_date(person_folder):
    """Получает дату решения из Информация.json."""
    info_file = person_folder / "Информация.json"
    if not info_file.exists():
        print("  > Файл 'Информация.json' не найден, используется стандартная дата.")
        return "неизвестной даты"
    try:
        with open(info_file, 'r', encoding='utf-8') as f:
            return json.load(f).get("Дата решения", "неизвестной даты")
    except Exception as e:
        print(f"  > Ошибка чтения 'Информация.json': {e}")
        return "неизвестной даты"

def setup_environment():
    """Настраивает прокси и API-ключ."""
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
    print(f"❌ Ошибка: Внутри '{people_dir}' должна быть ровно одна папка.")
    return None


def convert_image_to_pdf(image_path, output_pdf_path):
    """Конвертирует изображение в PDF."""
    try:
        with Image.open(image_path) as img:
            img.convert('RGB').save(output_pdf_path, "PDF", resolution=100.0)
        return True
    except Exception as e:
        print(f"❌ Ошибка конвертации {image_path.name}: {e}")
        return False


def upload_file_with_retry(file_path, max_retries=5):
    """Загружает файл с 5 попытками."""
    for attempt in range(max_retries):
        try:
            print(f"  > Загрузка файла '{file_path.name}' (попытка {attempt + 1})...")
            return genai.upload_file(path=file_path)
        except Exception as e:
            print(f"  > ❌ Ошибка при загрузке '{file_path.name}': {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
    return None


def cleanup_temp_files(files_to_delete):
    """Удаляет временные файлы."""
    for f in files_to_delete:
        try:
            if f and f.exists():
                f.unlink()
        except OSError:
            pass


# --- ЭТАП 1: ПОДГОТОВКА ФАЙЛОВ ---

def prepare_analysis_file(person_folder, model):
    """
    1. Делит ВСЕ большие файлы на части.
    2. Параллельно фильтрует "др" части, СОЗДАЕТ НОВЫЕ ФАЙЛЫ и УДАЛЯЕТ СТАРЫЕ.
    3. Объединяет отфильтрованное + остальное в один PDF.
    """
    materials_folder = person_folder / "Материалы дела"
    analysis_folder = person_folder / "Материалы дела Анализ"
    analysis_folder.mkdir(exist_ok=True)
    person_name = person_folder.name

    temp_files = []

    # 1. ПРЕДВАРИТЕЛЬНАЯ РАЗБИВКА ВСЕХ ФАЙЛОВ
    print("\n- Этап 1/3: Предварительная разбивка больших файлов...")
    all_source_files = list(materials_folder.glob("*.*"))
    file_to_chunks_map = {}  # Словарь для связи оригинального файла с его частями

    for file_path in all_source_files:
        try:
            if file_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
                target_pdf = analysis_folder / f"temp_conv_{file_path.stem}.pdf"
                if not convert_image_to_pdf(file_path, target_pdf): continue
                temp_files.append(target_pdf)
            else:
                target_pdf = file_path

            reader = PdfReader(target_pdf)
            if len(reader.pages) > 50:
                print(f"  > Файл '{file_path.name}' большой, делим на части...")
                parts = []
                for i, start_page in enumerate(range(0, len(reader.pages), 50)):
                    writer = PdfWriter()
                    end_page = min(start_page + 50, len(reader.pages))
                    for page_num in range(start_page, end_page):
                        writer.add_page(reader.pages[page_num])

                    chunk_path = analysis_folder / f"{target_pdf.stem}_part_{i + 1}.pdf"
                    with open(chunk_path, 'wb') as f_out:
                        writer.write(f_out)
                    parts.append(chunk_path)
                    temp_files.append(chunk_path)
                file_to_chunks_map[file_path] = parts
            else:
                file_to_chunks_map[file_path] = [target_pdf]
        except Exception as e:
            print(f"  > ⚠️  Не удалось обработать файл {file_path.name}: {e}")

    # 2. ПАРАЛЛЕЛЬНАЯ ФИЛЬТРАЦИЯ "ДР" ФАЙЛОВ
    print("\n- Этап 2/3: Параллельная фильтрация, переименование и замена 'др' файлов...")
    dr_keywords = ["др", "другие"]

    # Отбираем оригинальные "др" файлы для обработки
    dr_files_to_process = [f for f in all_source_files if any(kw in f.name.lower() for kw in dr_keywords)]
    # Все остальные файлы сразу идут в итоговый список
    final_pdf_paths = [chunk for f, chunks in file_to_chunks_map.items() if f not in dr_files_to_process for chunk in
                       chunks]

    def process_dr_file_thread(original_dr_file):
        chunks = file_to_chunks_map.get(original_dr_file)
        if not chunks: return

        merged_writer = PdfWriter()

        for chunk_path in chunks:
            uploaded_file = upload_file_with_retry(chunk_path)
            if not uploaded_file: continue
            try:
                prompt = f"""Анализ PDF. Найди ВСЕ страницы, относящиеся к {person_name}. Верни JSON: {{"relevant_pages": [номера_страниц]}}."""
                response = model.generate_content([uploaded_file, prompt], request_options={"timeout": 300})
                if not response.text or not response.text.strip():
                    continue
                result = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
                pages = result.get("relevant_pages", [])

                if pages:
                    reader = PdfReader(chunk_path)
                    for page_num in pages:
                        if 1 <= page_num <= len(reader.pages):
                            merged_writer.add_page(reader.pages[page_num - 1])
            except Exception as e:
                print(f"  > ❌ Ошибка при анализе части файла '{original_dr_file.name}': {e}")
            finally:
                genai.delete_file(uploaded_file.name)

        if len(merged_writer.pages) > 0:
            # --- ЛОГИКА ПЕРЕИМЕНОВАНИЯ И ЗАМЕНЫ ---
            original_stem = original_dr_file.stem
            words = original_stem.split()

            # Убираем последние 2 слова, если их больше двух
            if len(words) > 2:
                new_stem = " ".join(words[:-2])
                new_filename = new_stem + original_dr_file.suffix
                new_file_path = materials_folder / new_filename

                print(f"  > Создаю новый файл: '{new_filename}'")
                with open(new_file_path, 'wb') as f_out:
                    merged_writer.write(f_out)

                print(f"  > Удаляю старый файл: '{original_dr_file.name}'")
                original_dr_file.unlink()  # Удаляем оригинальный "др" файл

                final_pdf_paths.append(new_file_path)  # Добавляем новый файл для финального объединения
            else:
                # Если слов мало, просто сохраняем как есть, но в основную папку
                fallback_path = materials_folder / f"extracted_{original_dr_file.name}"
                with open(fallback_path, 'wb') as f_out:
                    merged_writer.write(f_out)
                final_pdf_paths.append(fallback_path)

    if dr_files_to_process:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            executor.map(process_dr_file_thread, dr_files_to_process)

    # 3. ОБЪЕДИНЕНИЕ В ИТОГОВЫЙ ФАЙЛ
    print("\n- Этап 3/3: Объединение всех подготовленных документов...")
    if not final_pdf_paths:
        return None, temp_files

    merger = PdfMerger()
    for pdf_path in final_pdf_paths:
        try:
            merger.append(str(pdf_path))
        except Exception as e:
            print(f"  > ⚠️  Не удалось добавить в сборку файл {pdf_path.name}: {e}")

    merged_pdf_path = analysis_folder / "Материалы дела (Общий).pdf"
    merger.write(str(merged_pdf_path))
    merger.close()
    print(f"✅ Создан итоговый файл для анализа: {merged_pdf_path.name}")
    return merged_pdf_path, temp_files


# --- ЗАДАЧИ АНАЛИЗА ---

def run_property_analysis_task(person_folder, model, merged_pdf_path):
    """Задача для анализа имущества с корректным форматом вывода для реализации."""
    print("\n>> (Поток 1) 🏠 Начинаю анализ ИМУЩЕСТВА...")
    uploaded_files_for_property = []
    temp_parts = []

    try:
        # Разбиваем и загружаем итоговый файл
        reader = PdfReader(merged_pdf_path)
        for i in range(0, len(reader.pages), 50):
            writer = PdfWriter()
            end_page = min(i + 50, len(reader.pages))
            for page_num in range(i, end_page):
                writer.add_page(reader.pages[page_num])
            part_path = merged_pdf_path.with_name(f"{merged_pdf_path.stem}_analysis_part_{i // 50 + 1}.pdf")
            with open(part_path, 'wb') as part_file:
                writer.write(part_file)
            temp_parts.append(part_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(upload_file_with_retry, temp_parts)
            uploaded_files_for_property = [r for r in results if r]

        if not uploaded_files_for_property:
            raise Exception("Не удалось загрузить части итогового файла.")

        # --- ЭТАПЫ 1 и 2 без изменений ---
        person_name = person_folder.name
        prompt1 = f"""На документах, найди абсолютно ВСЁ имущество {person_name}. Не упусти ничего. Верни JSON: {{"all_property": ["Имущество 1"]}}"""
        response1 = model.generate_content(uploaded_files_for_property + [prompt1], request_options={"timeout": 600})
        all_property = json.loads(response1.text.strip().replace("```json", "").replace("```", "")).get("all_property",
                                                                                                        [])

        if not all_property:
            print("  - 🏠 Имущество не найдено.")
            return

        prompt2 = f"""Из списка: {json.dumps(all_property, ensure_ascii=False)}, найди единственное жилье {person_name}. Верни JSON: {{"sole_residence": "Описание или null"}}"""
        response2 = model.generate_content(uploaded_files_for_property + [prompt2], request_options={"timeout": 400})
        sole_residence_data = json.loads(response2.text.strip().replace("```json", "").replace("```", ""))
        with open(person_folder / "Имущество (Единственное жилье).json", "w", encoding="utf-8") as f:
            json.dump(sole_residence_data, f, ensure_ascii=False, indent=4)

        # --- НАЧАЛО ИЗМЕНЕНИЯ: ЭТАП 3 ---
        property_for_sale = [p for p in all_property if p != sole_residence_data.get("sole_residence")]
        if property_for_sale:
            # 1. Используем ваш новый промпт
            # Я немного его улучшил, чтобы он мог обрабатывать несколько объектов, перечисляя их через запятую.
            prompt3 = f"""
Проанализируй судьбу этого имущества: {json.dumps(property_for_sale, ensure_ascii=False)}. 
Определи, было ли оно реализовано. 
Верни ответ СТРОГО в формате одного JSON-объекта с ключами "realized" и "unrealized".
В значении каждого ключа укажи названия объектов через запятую, если их несколько.

Пример вывода:
{{
    "realized": "Квартира по адресу Республика Бурятия, г. Улан-Удэ, ул. Волконского 1А",
    "unrealized": "Автомобиль Lada Vesta, Земельный участок по адресу ..."
}}

Пример вывода. если данных нет:
{{
    "realized": "",
    "unrealized": ""
}}
"""
            response3 = model.generate_content(uploaded_files_for_property + [prompt3],
                                               request_options={"timeout": 600})
            sale_data = json.loads(response3.text.strip().replace("```json", "").replace("```", ""))

            # 2. Создаем и сохраняем два отдельных JSON-файла, как вы и просили
            # Файл для реализованного имущества
            realized_output = {
                "realized": sale_data.get("realized", "-")
            }
            with open(person_folder / "Имущество (Реализованное).json", "w", encoding="utf-8") as f:
                json.dump(realized_output, f, ensure_ascii=False, indent=4)

            # Файл для нереализованного имущества
            unrealized_output = {
                "unrealized": sale_data.get("unrealized", "-")
            }
            with open(person_folder / "Имущество (Не реализованное).json", "w", encoding="utf-8") as f:
                json.dump(unrealized_output, f, ensure_ascii=False, indent=4)

        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

        print("  - ✅ 🏠 Анализ ИМУЩЕСТВА завершен.")

    except Exception as e:
        print(f"  - ❌ 🏠 Ошибка при анализе ИМУЩЕСТВА: {e}")
    finally:
        cleanup_temp_files(temp_parts)
        for f in uploaded_files_for_property:
            try:
                genai.delete_file(f.name)
            except Exception:
                pass


def run_income_analysis_task(person_folder, model):
    """Задача для анализа доходов с самым надежным промптом."""
    print("\n>> (Поток 2) 💰 Начинаю анализ ДОХОДОВ...")

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    file_path_str = filedialog.askopenfilename(title="Выберите файл с информацией о доходах (PDF, JPG, PNG)")
    root.destroy()

    if not file_path_str:
        print("  - 💰 Файл для доходов не выбран.")
        return

    income_file_path = Path(file_path_str)
    temp_income_pdf = None
    uploaded_file = None

    try:
        path_to_upload = income_file_path
        if income_file_path.suffix.lower() in ['.jpg', '.jpeg', '.png']:
            print(f"  > Обнаружен файл изображения '{income_file_path.name}', конвертируем в PDF...")
            analysis_folder = person_folder / "Материалы дела Анализ"
            analysis_folder.mkdir(exist_ok=True)
            temp_income_pdf = analysis_folder / f"temp_income_conversion_{income_file_path.stem}.pdf"
            if convert_image_to_pdf(income_file_path, temp_income_pdf):
                path_to_upload = temp_income_pdf
                print("  > Конвертация успешна.")
            else:
                print("  > ⚠️ Ошибка конвертации. Попытка анализа исходного изображения.")

        uploaded_file = upload_file_with_retry(path_to_upload)
        if not uploaded_file: return

        # --- НАЧАЛО ИЗМЕНЕНИЯ: НОВЫЙ УСИЛЕННЫЙ ПРОМПТ ---
        success = False
        max_retries = 5
        for attempt in range(max_retries):
            try:
                print(f"  > Анализ доходов (попытка {attempt + 1}/{max_retries})...")
                person_name = person_folder.name
                decision_date = get_decision_date(person_folder)
                current_date = datetime.now().strftime("%d.%m.%Y")

                # НОВЫЙ ПРОМПТ
                prompt = f"""
Твоя задача — извлечь данные о доходах (зарплата или пенсия) из документа и вернуть их СТРОГО в формате JSON.
Проанализируй документ для {person_name} за период с {decision_date} по {current_date}.

КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА ВЫВОДА:
1. Ответ должен быть ТОЛЬКО в формате JSON.
2. НЕ добавляй никаких пояснений, комментариев, markdown-разметки ```json``` или описания документа.
3. Если доходов в документе нет, верни пустой JSON-объект: {{}}.

ФОРМАТ JSON:
{{
  "date_of_receipt": "даты через точку с запятой",
  "source_of_receipt": "источники через точку с запятой (только 'зарплата' или 'пенсия')",
  "amount_of_the_receipt": "суммы через точку с запятой",
  "total": "итоговая сумма всех поступлений"
}}
"""

                response = model.generate_content([uploaded_file, prompt], request_options={"timeout": 600})

                if not response.text or not response.text.strip():
                    raise ValueError("Получен пустой ответ от API")

                text = response.text.strip().replace("```json", "").replace("```", "")
                income_data = json.loads(text)

                with open(person_folder / "Доходы.json", 'w', encoding='utf-8') as f:
                    json.dump(income_data, f, ensure_ascii=False, indent=4)

                print("  - ✅ 💰 Анализ ДОХОДОВ в формате JSON успешно завершен.")
                success = True
                break

            except (json.JSONDecodeError, ValueError) as e:
                print(f"  - ⚠️  Ошибка при получении JSON (попытка {attempt + 1}): {e}")
                if 'response' in locals() and hasattr(response, 'text'):
                    print(f"      > Ответ от API был: '{response.text[:200]}...'")
                if attempt < max_retries - 1:
                    time.sleep(3)

        if not success:
            print("  - ❌ 💰 Не удалось получить JSON-ответ после нескольких попыток.")

    except Exception as e:
        print(f"  - ❌ 💰 Произошла непредвиденная ошибка в процессе анализа доходов: {e}")
    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception:
                pass
        if temp_income_pdf:
            cleanup_temp_files([temp_income_pdf])


# --- ГЛАВНАЯ ФУНКЦИЯ-ОРКЕСТРАТОР ---

def main():
    if not setup_environment(): return
    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    person_folder = find_person_folder()
    if not person_folder: return

    temp_files_to_clean = []
    try:
        merged_pdf_path, temp_files_to_clean = prepare_analysis_file(person_folder, model)

        print("\n--- Запуск основных задач анализа в параллельном режиме ---")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            if merged_pdf_path:
                executor.submit(run_property_analysis_task, person_folder, model, merged_pdf_path)
            else:
                print(">> Пропуск анализа имущества: не удалось создать итоговый файл.")

            executor.submit(run_income_analysis_task, person_folder, model)

        print("\n--- Все задачи анализа завершены ---")

    except Exception as e:
        print(f"❌ Произошла общая ошибка в main: {e}")
    finally:
        print("\n- Финальная очистка...")
        cleanup_temp_files(temp_files_to_clean)
        print("✅ Очистка завершена.")


if __name__ == "__main__":
    main()