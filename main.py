import subprocess
import sys

# Запуск другого Python-файла
get_files_to_person = subprocess.run([sys.executable, "get_files_to_person.py"],
                       capture_output=True, text=True)

if get_files_to_person.stderr:
    print("Ошибки:", get_files_to_person.stderr)

# Запуск другого Python-файла
get_info_about_person = subprocess.run([sys.executable, "get_info_about_person.py"],
                       capture_output=True, text=True)

if get_info_about_person.stderr:
    print("Ошибки:", get_info_about_person.stderr)