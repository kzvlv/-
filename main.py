import subprocess
import sys

# Запуск Python-файла
get_files_to_person = subprocess.run([sys.executable, "get_files_to_person.py"],
                       capture_output=True, text=True)

if get_files_to_person.stderr:
    print("Ошибки:", get_files_to_person.stderr)

# Запуск Python-файла
get_info_about_person = subprocess.run([sys.executable, "get_info_about_person.py"],
                       capture_output=True, text=True)

if get_info_about_person.stderr:
    print("Ошибки:", get_info_about_person.stderr)

# Запуск Python-файла
get_kommersant = subprocess.run([sys.executable, "get_kommersant.py"],
                       capture_output=True, text=True)

if get_kommersant.stderr:
    print("Ошибки:", get_kommersant.stderr)

# Запуск Python-файла
promt_to_AI_creditors = subprocess.run([sys.executable, "promt_to_AI_creditors.py"],
                       capture_output=True, text=True)

if promt_to_AI_creditors.stderr:
    print("Ошибки:", promt_to_AI_creditors.stderr)


# Запуск Python-файла
promts_to_AI_property = subprocess.run([sys.executable, "promts_to_AI_property.py"],
                       capture_output=True, text=True)

if promts_to_AI_property.stderr:
    print("Ошибки:", promts_to_AI_property.stderr)