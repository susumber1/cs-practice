"""Простое оконное приложение для русскоязычного OCR."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import raspoznat_pechat as ocr


ТИПЫ_ФАЙЛОВ = (
    (
        "Фото и PDF",
        (
            "*.jpg", "*.JPG", "*.jpeg", "*.JPEG", "*.png", "*.PNG",
            "*.heic", "*.HEIC", "*.pdf", "*.PDF",
        ),
    ),
    ("Все файлы", "*"),
)


class ПриложениеOCR:
    def __init__(self, окно: tk.Tk):
        self.окно = окно
        self.окно.title("Распознавание печатного текста")
        self.окно.geometry("1000x720")
        self.окно.minsize(760, 520)

        self.путь = tk.StringVar()
        self.диплом = tk.BooleanVar(value=False)
        self.проверка = tk.BooleanVar(value=False)
        self.очередь: queue.Queue = queue.Queue()
        self.занято = False

        self._создать_интерфейс()
        self.окно.protocol("WM_DELETE_WINDOW", self._закрыть)

    def _создать_интерфейс(self) -> None:
        основной = ttk.Frame(self.окно, padding=16)
        основной.grid(row=0, column=0, sticky="nsew")
        self.окно.rowconfigure(0, weight=1)
        self.окно.columnconfigure(0, weight=1)
        основной.columnconfigure(0, weight=1)
        основной.rowconfigure(3, weight=1)

        ttk.Label(
            основной,
            text="Распознавание печатного текста",
            font=("TkDefaultFont", 17, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        выбор = ttk.Frame(основной)
        выбор.grid(row=1, column=0, sticky="ew")
        выбор.columnconfigure(0, weight=1)
        self.поле_пути = ttk.Entry(выбор, textvariable=self.путь, state="readonly")
        self.поле_пути.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.кнопка_выбрать = ttk.Button(
            выбор, text="Выбрать фото или PDF…", command=self._выбрать_файл
        )
        self.кнопка_выбрать.grid(row=0, column=1, sticky="ew")

        параметры = ttk.Frame(основной)
        параметры.grid(row=2, column=0, sticky="ew", pady=(10, 8))
        ttk.Checkbutton(
            параметры,
            text="Диплом ЮФУ по шаблону",
            variable=self.диплом,
        ).grid(row=0, column=0, sticky="w", padx=(0, 18))
        ttk.Checkbutton(
            параметры,
            text="Проверить текст после распознавания",
            variable=self.проверка,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            параметры,
            text=(
                "Для диплома используется словарь; для обычного текста — отдельная "
                "модель коррекции."
            ),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        панель_результата = ttk.LabelFrame(
            основной, text="Распознанный текст", padding=(8, 8)
        )
        панель_результата.grid(row=3, column=0, sticky="nsew")
        панель_результата.rowconfigure(0, weight=1)
        панель_результата.columnconfigure(0, weight=1)
        self.результат = ScrolledText(
            панель_результата,
            wrap="word",
            font=("TkDefaultFont", 13),
            padx=8,
            pady=8,
            undo=False,
        )
        self.результат.grid(row=0, column=0, sticky="nsew")

        нижняя_панель = ttk.Frame(основной)
        нижняя_панель.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        нижняя_панель.columnconfigure(0, weight=1)
        self.статус = ttk.Label(нижняя_панель, text="Выберите изображение или PDF.")
        self.статус.grid(row=0, column=0, sticky="w")
        self.кнопка_копировать = ttk.Button(
            нижняя_панель,
            text="Копировать",
            command=self._копировать,
            state="disabled",
        )
        self.кнопка_копировать.grid(row=0, column=1, padx=(8, 0))
        self.кнопка_сохранить = ttk.Button(
            нижняя_панель,
            text="Сохранить TXT…",
            command=self._сохранить,
            state="disabled",
        )
        self.кнопка_сохранить.grid(row=0, column=2, padx=(8, 0))
        self.кнопка_распознать = ttk.Button(
            нижняя_панель,
            text="Распознать",
            command=self._начать_распознавание,
            state="disabled",
            default="active",
        )
        self.кнопка_распознать.grid(row=0, column=3, padx=(8, 0))

    def _выбрать_файл(self) -> None:
        выбранный = filedialog.askopenfilename(
            parent=self.окно,
            title="Выберите фото или PDF",
            filetypes=ТИПЫ_ФАЙЛОВ,
        )
        if выбранный:
            self.путь.set(выбранный)
            self.результат.delete("1.0", tk.END)
            self.кнопка_копировать.configure(state="disabled")
            self.кнопка_сохранить.configure(state="disabled")
            self.кнопка_распознать.configure(state="normal")
            self.статус.configure(text="Файл выбран. Нажмите «Распознать».")

    def _начать_распознавание(self) -> None:
        путь = Path(self.путь.get())
        if not путь.is_file():
            messagebox.showerror("Файл не найден", "Выберите доступное фото или PDF.")
            return

        self.занято = True
        self.кнопка_выбрать.configure(state="disabled")
        self.кнопка_распознать.configure(state="disabled")
        self.кнопка_копировать.configure(state="disabled")
        self.кнопка_сохранить.configure(state="disabled")
        self.результат.delete("1.0", tk.END)
        self.статус.configure(text="Распознаю… Это может занять некоторое время.")

        поток = threading.Thread(
            target=self._распознать_в_фоне,
            args=(путь, self.диплом.get(), self.проверка.get()),
            daemon=True,
        )
        поток.start()
        self.окно.after(120, self._проверить_очередь)

    def _распознать_в_фоне(
        self, путь: Path, режим_диплома: bool, проверять: bool
    ) -> None:
        try:
            корректор = (
                ocr.РусскийКорректор() if проверять and not режим_диплома else None
            )
            текст = ocr.распознать(
                путь,
                шаблон_диплома=режим_диплома,
                корректор=корректор,
                словарная_проверка_диплома=проверять,
            )
            self.очередь.put(("готово", текст))
        except Exception as ошибка:
            self.очередь.put(("ошибка", str(ошибка)))

    def _проверить_очередь(self) -> None:
        try:
            тип, сообщение = self.очередь.get_nowait()
        except queue.Empty:
            if self.занято:
                self.окно.after(120, self._проверить_очередь)
            return

        self.занято = False
        self.кнопка_выбрать.configure(state="normal")
        self.кнопка_распознать.configure(state="normal")
        if тип == "готово":
            self.результат.insert("1.0", сообщение)
            есть_текст = bool(сообщение.strip())
            self.кнопка_копировать.configure(
                state="normal" if есть_текст else "disabled"
            )
            self.кнопка_сохранить.configure(
                state="normal" if есть_текст else "disabled"
            )
            self.статус.configure(text="Готово." if есть_текст else "Текст не найден.")
        else:
            self.статус.configure(text="Не удалось распознать файл.")
            messagebox.showerror("Ошибка распознавания", сообщение)

    def _получить_текст(self) -> str:
        return self.результат.get("1.0", "end-1c")

    def _копировать(self) -> None:
        текст = self._получить_текст()
        if текст:
            self.окно.clipboard_clear()
            self.окно.clipboard_append(текст)
            self.статус.configure(text="Текст скопирован в буфер обмена.")

    def _сохранить(self) -> None:
        исходный_путь = Path(self.путь.get()) if self.путь.get() else None
        имя = f"{исходный_путь.stem}_result.txt" if исходный_путь else "result.txt"
        путь = filedialog.asksaveasfilename(
            parent=self.окно,
            title="Сохранить распознанный текст",
            defaultextension=".txt",
            initialfile=имя,
            filetypes=(("Текстовый файл", "*.txt"),),
        )
        if not путь:
            return
        try:
            Path(путь).write_text(self._получить_текст() + "\n", encoding="utf-8")
        except OSError as ошибка:
            messagebox.showerror("Не удалось сохранить файл", str(ошибка))
            return
        self.статус.configure(text=f"Сохранено: {путь}")

    def _закрыть(self) -> None:
        if self.занято and not messagebox.askyesno(
            "Распознавание выполняется",
            "Закрыть окно до завершения распознавания?",
            parent=self.окно,
        ):
            return
        self.окно.destroy()


def main() -> None:
    окно = tk.Tk()
    ПриложениеOCR(окно)
    окно.mainloop()


if __name__ == "__main__":
    main()
