import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import shutil
from pathlib import Path


class DebtorFileManager:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Добавление должника - 3 этапа")
        self.root.geometry("700x500")

        self.full_name = ""
        self.materials_files = []
        self.decision_files = []
        self.inclusion_files = []

        self.current_stage = 0  # 0: ФИО, 1: Материалы, 2: Решение, 3: Включение
        self.stages = ["Ввод ФИО", "Материалы дела", "Решение", "О включении"]

        self.setup_ui()

    def setup_ui(self):
        # Заголовок
        self.title_label = tk.Label(self.root, text="Добавление должника", font=("Arial", 16, "bold"))
        self.title_label.pack(pady=20)

        # Индикатор этапов
        self.stage_label = tk.Label(self.root, text=f"Этап 1/4: {self.stages[0]}", font=("Arial", 12), fg="blue")
        self.stage_label.pack(pady=10)

        # Поле для ввода ФИО
        tk.Label(self.root, text="Полное ФИО должника:", font=("Arial", 12)).pack(pady=5)

        self.name_entry = tk.Entry(self.root, width=50, font=("Arial", 12))
        self.name_entry.pack(pady=10)
        self.name_entry.bind("<Return>", lambda e: self.next_stage())

        # Кнопка далее
        self.next_btn = tk.Button(
            self.root,
            text="Далее →",
            command=self.next_stage,
            font=("Arial", 12),
            bg="#4CAF50",
            fg="white",
            width=15
        )
        self.next_btn.pack(pady=20)

        # Информация о выбранных файлах
        self.info_frame = tk.Frame(self.root)
        self.info_frame.pack(pady=10, fill=tk.X, padx=20)

        self.materials_info = tk.Label(self.info_frame, text="Материалы дела: не выбраны", font=("Arial", 10),
                                       anchor="w")
        self.materials_info.pack(fill=tk.X, pady=2)

        self.decision_info = tk.Label(self.info_frame, text="Решение: не выбрано", font=("Arial", 10), anchor="w")
        self.decision_info.pack(fill=tk.X, pady=2)

        self.inclusion_info = tk.Label(self.info_frame, text="О включении: не выбраны", font=("Arial", 10), anchor="w")
        self.inclusion_info.pack(fill=tk.X, pady=2)

        # Кнопка сохранения
        self.save_btn = tk.Button(
            self.root,
            text="Сохранить все файлы",
            command=self.save_all_files,
            font=("Arial", 12),
            bg="#FF9800",
            fg="white",
            width=20,
            state="disabled"
        )
        self.save_btn.pack(pady=20)

        # Статус
        self.status_label = tk.Label(self.root, text="Введите ФИО должника и нажмите 'Далее'", font=("Arial", 10),
                                     fg="gray")
        self.status_label.pack(pady=10)

    def next_stage(self):
        if self.current_stage == 0:  # Переход от ФИО к Материалам
            self.full_name = self.name_entry.get().strip()
            if not self.full_name:
                messagebox.showerror("Ошибка", "Введите ФИО должника!")
                return

            self.current_stage = 1
            self.stage_label.config(text=f"Этап 2/4: {self.stages[1]}")
            self.select_materials()

        elif self.current_stage == 1:  # Переход от Материалов к Решению
            if not self.materials_files:
                messagebox.showwarning("Внимание", "Вы не выбрали материалы дела. Продолжить?")

            self.current_stage = 2
            self.stage_label.config(text=f"Этап 3/4: {self.stages[2]}")
            self.select_decision()

        elif self.current_stage == 2:  # Переход от Решения к Включению
            if not self.decision_files:
                messagebox.showwarning("Внимание", "Вы не выбрали решение. Продолжить?")

            self.current_stage = 3
            self.stage_label.config(text=f"Этап 4/4: {self.stages[3]}")
            self.select_inclusion()

        elif self.current_stage == 3:  # Все этапы завершены
            self.enable_save_button()

    def select_materials(self):
        """Выбор материалов дела (PDF и JPG)"""
        filetypes = [
            ("Материалы дела", "*.pdf *.jpg *.jpeg"),
            ("PDF файлы", "*.pdf"),
            ("Изображения", "*.jpg *.jpeg"),
            ("Все файлы", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Этап 2/4: Выберите материалы дела (PDF, JPG)",
            filetypes=filetypes
        )

        if files:
            self.materials_files = list(files)
            self.materials_info.config(text=f"Материалы дела: {len(self.materials_files)} файл(ов)")

        self.next_btn.config(text="Далее →")
        self.status_label.config(text="Материалы выбраны. Нажмите 'Далее' для перехода к Решению")

    def select_decision(self):
        """Выбор решения (только PDF)"""
        filetypes = [
            ("Решение", "*.pdf"),
            ("PDF файлы", "*.pdf"),
            ("Все файлы", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Этап 3/4: Выберите решение (PDF)",
            filetypes=filetypes
        )

        if files:
            self.decision_files = list(files)
            self.decision_info.config(text=f"Решение: {len(self.decision_files)} файл(ов)")

        self.next_btn.config(text="Далее →")
        self.status_label.config(text="Решение выбрано. Нажмите 'Далее' для перехода к Включению")

    def select_inclusion(self):
        """Выбор файлов 'О включении' (PDF)"""
        filetypes = [
            ("О включении", "*.pdf"),
            ("PDF файлы", "*.pdf"),
            ("Все файлы", "*.*")
        ]

        files = filedialog.askopenfilenames(
            title="Этап 4/4: Выберите файлы 'О включении' (PDF)",
            filetypes=filetypes
        )

        if files:
            self.inclusion_files = list(files)
            self.inclusion_info.config(text=f"О включении: {len(self.inclusion_files)} файл(ов)")

        self.next_btn.config(text="Завершить")
        self.status_label.config(text="Все этапы завершены. Нажмите 'Сохранить все файлы'")
        self.enable_save_button()

    def enable_save_button(self):
        """Активирует кнопку сохранения когда все готово"""
        if self.full_name:
            self.save_btn.config(state="normal")

    def save_all_files(self):
        """Сохраняет все файлы согласно требованиям"""
        try:
            # Создаем основную структуру папок
            base_dir = Path("people") / self.full_name
            materials_dir = base_dir / "Материалы дела"
            decision_dir = base_dir / "Решение"
            inclusion_dir = base_dir / "О включении"

            # Создаем все папки
            materials_dir.mkdir(parents=True, exist_ok=True)
            decision_dir.mkdir(parents=True, exist_ok=True)
            inclusion_dir.mkdir(parents=True, exist_ok=True)

            saved_count = 0

            # Сохраняем материалы дела
            for i, file_path in enumerate(self.materials_files, 1):
                try:
                    source = Path(file_path)
                    dest = materials_dir / source.name
                    shutil.copy2(source, dest)
                    saved_count += 1
                except Exception as e:
                    print(f"Ошибка при копировании материала {file_path}: {e}")

            # Сохраняем решение (переименовываем в Решение.pdf)
            for i, file_path in enumerate(self.decision_files, 1):
                try:
                    source = Path(file_path)
                    dest = decision_dir / "Решение.pdf"
                    shutil.copy2(source, dest)
                    saved_count += 1
                except Exception as e:
                    print(f"Ошибка при копировании решения {file_path}: {e}")

            # Сохраняем файлы о включении (переименовываем)
            for i, file_path in enumerate(self.inclusion_files, 1):
                try:
                    source = Path(file_path)
                    if len(self.inclusion_files) == 1:
                        dest_name = "О включении.pdf"
                    else:
                        dest_name = f"О включении {i}.pdf"

                    dest = inclusion_dir / dest_name
                    shutil.copy2(source, dest)
                    saved_count += 1
                except Exception as e:
                    print(f"Ошибка при копировании включения {file_path}: {e}")

            # Показываем результат
            messagebox.showinfo(
                "Успех!",
                f"Все файлы сохранены!\n\n"
                f"ФИО: {self.full_name}\n"
                f"Сохранено файлов: {saved_count}\n"
                f"Путь: {base_dir.absolute()}\n\n"
                f"Структура:\n"
                f"• Материалы дела: {len(self.materials_files)} файл(ов)\n"
                f"• Решение: {len(self.decision_files)} файл(ов)\n"
                f"• О включении: {len(self.inclusion_files)} файл(ов)"
            )

            self.reset_application()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить файлы: {e}")

    def reset_application(self):
        """Сбрасывает приложение для нового ввода"""
        self.full_name = ""
        self.materials_files = []
        self.decision_files = []
        self.inclusion_files = []
        self.current_stage = 0

        self.name_entry.delete(0, tk.END)
        self.materials_info.config(text="Материалы дела: не выбраны")
        self.decision_info.config(text="Решение: не выбрано")
        self.inclusion_info.config(text="О включении: не выбраны")
        self.stage_label.config(text=f"Этап 1/4: {self.stages[0]}")
        self.next_btn.config(text="Далее →")
        self.save_btn.config(state="disabled")
        self.status_label.config(text="Введите ФИО должника и нажмите 'Далее'")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    # Создаем основную папку если её нет
    os.makedirs("people", exist_ok=True)

    app = DebtorFileManager()
    app.run()