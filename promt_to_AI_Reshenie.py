# Финальная версия, исправленная благодаря вашему открытию.
# Ключевое исправление: genai.configure() вызывается ПОСЛЕ установки прокси.

import os
import json
from pathlib import Path
import google.generativeai as genai
import time


with open('autorization\\proxy.txt', 'r', encoding='utf-8') as file:
    proxy = file.read().split(":")
    PROXY_ADDRESS = proxy[0]
    PROXY_PORT = proxy[1]
    PROXY_LOGIN = proxy[2]
    PROXY_PASSWORD = proxy[3]
with open('autorization\\API_GEMINI.txt', 'r', encoding='utf-8') as file:
    GOOGLE_API_KEY = file.read()



# --- КОНЕЦ НАСТРОЕК ---

def setup_environment():
    """Настраивает прокси и API-ключ в правильном порядке."""
    try:
        if PROXY_ADDRESS:
            proxy_url = f"http://{PROXY_LOGIN}:{PROXY_PASSWORD}@{PROXY_ADDRESS}:{PROXY_PORT}"
            # 1. Сначала устанавливаем прокси
            os.environ['HTTPS_PROXY'] = proxy_url
            os.environ['HTTP_PROXY'] = proxy_url
            print(f"🚀 Прокси установлен: {PROXY_ADDRESS}:{PROXY_PORT}")

        # 2. И только потом конфигурируем библиотеку
        genai.configure(api_key=GOOGLE_API_KEY)
        print("✅ Конфигурация Google AI прошла успешно.")
        return True

    except Exception as e:
        print(f"❌ Ошибка конфигурации: {e}")
        return False


# ... (остальной код остается без изменений) ...

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


def analyze_pdf(pdf_path: Path, model):
    """Анализирует один PDF-файл и возвращает результат."""
    print(f"  > Загрузка файла '{pdf_path.name}'...")
    uploaded_file = None
    try:
        uploaded_file = genai.upload_file(path=pdf_path)
        print(f"  > Файл загружен. Анализ...")

        prompt_text = """
        Проанализируй PDF-документ. Твоя задача - извлечь информацию о кредиторе. Важно, что к Неустойке относятся только пени и штрафы, все остальное к основному долгу. Также ВАЖНО, что сумма Неустойки и Основного долга равна сумме общего долга! Скорее всего 2-ой очереди н будет, а 3-я будет почти всегда! Для десятичных дробей используй точку! Используй код питон для подсчета, а не считай в "голове"!!!
        Верни ответ СТРОГО в формате JSON. Не добавляй никаких пояснений, комментариев или markdown-форматирования ```json ```. Только чистый JSON.
        
        Пример требуемого формата:
        {
          "Наименование кредитора": "ПАО Сбербанк",
          "Сумма основного долга 2-ой очереди": "0.00",
          "Сумма неустойки 2-ой очереди": "0.00"
          "Сумма основного долга 3-ей очереди": "15425.23",
          "Сумма неустойки 3-ей очереди": "3.1215"
        }
        
        Если не можешь найти какую-то сумму, укажи "0.00".
        Наименование кредитора должно быть максимально точным и кратким.(Что-то вроде ПАО Сбербанк или ООО МКК Феникс)
        """


        response = model.generate_content([uploaded_file, prompt_text], request_options={"timeout": 600})
        response_text = response.text.strip().replace("```json", "").replace("```", "").strip()

        return json.loads(response_text)

    except Exception as e:
        print(f"  > ❌ Ошибка при анализе '{pdf_path.name}': {e}")
        return None
    finally:
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
            except Exception as e:
                pass  # Ошибки при удалении можно игнорировать


def main():
    if not setup_environment():
        return

    model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")
    person_folder = find_person_folder()
    if not person_folder:
        return

    inclusion_folder = person_folder / "О включении"
    if not inclusion_folder.is_dir():
        print(f"Папка 'О включении' не найдена в '{person_folder}'.")
        return

    analysis_folder = person_folder / "О включении Анализ"
    analysis_folder.mkdir(exist_ok=True)
    print(f"📂 Результаты будут сохранены в: {analysis_folder.resolve()}")

    for pdf_path in sorted(inclusion_folder.glob("*.pdf")):
        print(f"\n--- Обработка файла: {pdf_path.name} ---")
        analysis_result = analyze_pdf(pdf_path, model)
        if analysis_result and isinstance(analysis_result, dict):
            creditor_name = analysis_result.get("Наименование кредитора", "неизвестный_кредитор")
            safe_creditor_name = "".join(c for c in creditor_name if c.isalnum() or c in " -").rstrip()
            output_filename = analysis_folder / f"{safe_creditor_name}.json"
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(analysis_result, f, ensure_ascii=False, indent=4)
            print(f"  > ✅ Результат сохранен в: {output_filename}")


if __name__ == "__main__":
    main()