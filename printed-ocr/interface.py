"""Оконное приложение для распознавания комплектов документов."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from rounded_widgets import Карточка, Кнопка, ПолосаПрокрутки, Прогресс
from appearance import (
    АКЦЕНТЫ, РАЗМЕРЫ, ТЕМЫ, Оформление, загрузить_оформление, сохранить_оформление,
)

from document_batch import (
    расширения_раздела,
    форматы_раздела,
    ТИПЫ_ДОКУМЕНТОВ,
    Задание,
    РезультатФайла,
    СеансРаспознавания,
    собрать_результаты,
)


def типы_файлов(раздел: str):
    шаблоны = tuple(шаблон for расширение in sorted(расширения_раздела(раздел))
                    for шаблон in (f"*{расширение}", f"*{расширение.upper()}"))
    return (("Фото, PDF и DOCX" if раздел == "curriculum" else "Фото и PDF", шаблоны),
            ("Все файлы", "*"))


# Семантические роли: цвета меняются без пересоздания виджетов.
ФОН = "background"
ПОВЕРХНОСТЬ = "surface"
ТЕКСТ = "text"
ВТОРИЧНЫЙ = "muted"


def число_файлов(число: int) -> str:
    if 11 <= число % 100 <= 14:
        слово = "файлов"
    else:
        слово = {1: "файл", 2: "файла", 3: "файла", 4: "файла"}.get(
            число % 10, "файлов"
        )
    return f"{число} {слово}"


class ПриложениеOCR:
    def __init__(self, окно: tk.Tk):
        self.окно = окно
        окно.title("Распознавание печатного текста")
        окно.geometry("1240x860")
        окно.minsize(1000, 740)
        self.оформление = загрузить_оформление()
        self._надписи = []
        self._компоненты = []
        self._меню = []
        self._окно_оформления = None
        self.шрифт = tkfont.nametofont("TkDefaultFont").actual("family")
        self.типы = {тип.код: тип for тип in ТИПЫ_ДОКУМЕНТОВ}
        self.файлы: dict[str, list[Path]] = {код: [] for код in self.типы}
        self.раздел = ТИПЫ_ДОКУМЕНТОВ[0].код
        self.результаты: list[РезультатФайла] = []
        self._число_символов = 0
        self.сеанс = СеансРаспознавания()
        self.очередь: queue.Queue = queue.Queue()
        self.остановка = threading.Event()
        self.занято = False
        self.проверка = tk.BooleanVar(value=True)
        self.диплом = tk.BooleanVar(value=True)
        self.сверка = tk.BooleanVar(value=True)
        self.отчёт_сверки = ""
        self.папка_выбора = Path.home()
        self._стили()
        self._создать_интерфейс()
        self._выбрать_раздел(self.раздел)
        окно.protocol("WM_DELETE_WINDOW", self._закрыть)
        for сочетание in ("<Command-o>", "<Control-o>"):
            окно.bind(сочетание, lambda событие: self._добавить_файлы())

    def _стили(self) -> None:
        п = self.оформление.палитра
        р = self.оформление.шрифт
        стиль = ttk.Style(self.окно)
        if стиль.theme_use() != "clam":
            стиль.theme_use("clam")
        self.окно.configure(background=п[ФОН])
        стиль.configure(".", background=п[ФОН], foreground=п[ТЕКСТ],
                         font=(self.шрифт, р(11)), borderwidth=0,
                         bordercolor=п[ФОН], lightcolor=п[ФОН], darkcolor=п[ФОН])
        стиль.configure("TFrame", background=п[ФОН])
        стиль.configure("Card.TFrame", background=п[ПОВЕРХНОСТЬ])
        стиль.configure("TLabel", background=п[ФОН], foreground=п[ТЕКСТ],
                         font=(self.шрифт, р(12)))
        стиль.configure("Muted.TLabel", foreground=п[ВТОРИЧНЫЙ], font=(self.шрифт, р(10)))
        # Удаляем системный field-элемент: clam рисует светлую рамку даже при borderwidth=0.
        стиль.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        стиль.configure("Treeview", background=п["field"], fieldbackground=п["field"],
                         foreground=п[ТЕКСТ], rowheight=34 + 2 * (р(11) - 11),
                         borderwidth=0, relief="flat", font=(self.шрифт, р(11)))
        стиль.layout("Treeview.Heading", [("Treeheading.padding", {"sticky": "nswe", "children": [
            ("Treeheading.text", {"sticky": "we"}),
        ]})])
        стиль.configure("Treeview.Heading", background=п["field"], foreground=п[ВТОРИЧНЫЙ],
                         relief="flat", padding=(8, 10), font=(self.шрифт, р(10), "bold"))
        стиль.map("Treeview", background=[("selected", п["selection"])],
                    foreground=[("selected", п[ТЕКСТ])])
        стиль.configure("TPanedwindow", background=п[ФОН])
        стиль.configure("Sash", sashthickness=12, background=п[ФОН], gripcount=0)
        for виджет, размер, жирный, цвет, фон in self._надписи:
            if виджет.winfo_exists():
                виджет.configure(background=п[фон], foreground=п[цвет],
                                  font=(self.шрифт, р(размер), "bold" if жирный else "normal"))
        self._компоненты = [в for в in self._компоненты if в.winfo_exists()]
        for виджет in self._компоненты:
            виджет.оформить(п, (self.шрифт, р(11)))
        self._меню = [м for м in self._меню if м.winfo_exists()]
        for меню in self._меню:
            меню.configure(background=п[ПОВЕРХНОСТЬ], foreground=п[ТЕКСТ],
                            activebackground=п["selection"], activeforeground=п[ТЕКСТ],
                            font=(self.шрифт, р(11)), borderwidth=0, relief="flat")
        if hasattr(self, "результат"):
            self.результат.configure(background=п["field"], foreground=п[ТЕКСТ],
                                     insertbackground=п[ТЕКСТ], selectbackground=п["selection"],
                                     selectforeground=п[ТЕКСТ], font=(self.шрифт, р(12)))

    def _кнопка(self, родитель, текст, команда, *, фон=ФОН, акцент=False, state="normal"):
        кнопка = Кнопка(родитель, text=текст, command=команда, палитра=self.оформление.палитра,
                         font=(self.шрифт, self.оформление.шрифт(11)), фон=фон,
                         акцент=акцент, state=state)
        self._компоненты.append(кнопка)
        return кнопка

    def _карточка(self, родитель, **параметры):
        виджет = Карточка(родитель, палитра=self.оформление.палитра, **параметры)
        self._компоненты.append(виджет)
        return виджет

    def _полоса(self, родитель, команда):
        виджет = ПолосаПрокрутки(родитель, command=команда, палитра=self.оформление.палитра)
        self._компоненты.append(виджет)
        return виджет

    def _новое_меню(self, родитель):
        п = self.оформление.палитра
        меню = tk.Menu(родитель, tearoff=False, background=п[ПОВЕРХНОСТЬ], foreground=п[ТЕКСТ],
                        activebackground=п["selection"], activeforeground=п[ТЕКСТ],
                        font=(self.шрифт, self.оформление.шрифт(11)), borderwidth=0, relief="flat")
        self._меню.append(меню)
        return меню

    @staticmethod
    def _показать_меню(кнопка, меню):
        try:
            меню.tk_popup(кнопка.winfo_rootx(), кнопка.winfo_rooty()+кнопка.winfo_height()+4)
        finally:
            меню.grab_release()

    def _надпись(self, родитель, текст="", *, размер=12, жирный=False,
                 цвет=ТЕКСТ, фон=ПОВЕРХНОСТЬ, **параметры) -> tk.Label:
        п = self.оформление.палитра
        виджет = tk.Label(родитель, text=текст, background=п[фон], foreground=п[цвет],
                          font=(self.шрифт, self.оформление.шрифт(размер),
                                "bold" if жирный else "normal"),
                          anchor="w", justify="left", **параметры)
        self._надписи.append((виджет, размер, жирный, цвет, фон))
        return виджет

    def _настроить_оформление(self) -> None:
        if self._окно_оформления is not None:
            self._окно_оформления.lift()
            return
        диалог = tk.Toplevel(self.окно)
        self._окно_оформления = диалог
        диалог.title("Оформление")
        диалог.transient(self.окно)
        диалог.resizable(False, False)
        диалог.configure(background=self.оформление.палитра[ФОН])
        панель = ttk.Frame(диалог, padding=24)
        панель.pack(fill="both", expand=True)
        панель.columnconfigure(1, weight=1)
        значения = {}
        for строка, (ключ, подпись, варианты) in enumerate((
            ("тема", "Тема", ТЕМЫ), ("акцент", "Акцентный цвет", АКЦЕНТЫ),
            ("размер", "Размер текста", РАЗМЕРЫ),
        )):
            ttk.Label(панель, text=подпись).grid(row=строка, column=0, sticky="w", padx=(0, 18), pady=8)
            переменная = tk.StringVar(master=диалог, value=getattr(self.оформление, ключ))
            значения[ключ] = переменная
            меню = self._новое_меню(диалог)
            кнопка = self._кнопка(панель, переменная.get() + "  ▾", lambda: None)
            кнопка.command = lambda к=кнопка, м=меню: self._показать_меню(к, м)
            кнопка.grid(row=строка, column=1, sticky="ew", pady=8)
            for вариант in варианты:
                меню.add_radiobutton(label=вариант, variable=переменная, value=вариант)
            переменная.trace_add("write", lambda *args, к=кнопка, п=переменная:
                                 к.configure(text=п.get() + "  ▾"))
        ttk.Label(панель, text="Выбор сохранится для следующих запусков.",
                  style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 18))
        кнопки = ttk.Frame(панель)
        кнопки.grid(row=4, column=0, columnspan=2, sticky="ew")

        def закрыть():
            self._окно_оформления = None
            диалог.destroy()
            self._компоненты = [в for в in self._компоненты if в.winfo_exists()]
            self._меню = [м for м in self._меню if м.winfo_exists()]

        def сбросить():
            исходные = Оформление()
            for ключ, переменная in значения.items():
                переменная.set(getattr(исходные, ключ))

        def применить():
            настройки = Оформление(**{ключ: переменная.get() for ключ, переменная in значения.items()})
            try:
                сохранить_оформление(настройки)
            except OSError as ошибка:
                messagebox.showerror("Не удалось сохранить оформление", str(ошибка), parent=диалог)
                return
            self.оформление = настройки
            self._стили()
            закрыть()

        self._кнопка(кнопки, "Сбросить", сбросить).pack(side="left")
        self._кнопка(кнопки, "Сохранить", применить, акцент=True).pack(side="right")
        self._кнопка(кнопки, "Отмена", закрыть).pack(side="right", padx=8)
        диалог.protocol("WM_DELETE_WINDOW", закрыть)
        диалог.bind("<Escape>", lambda событие: закрыть())
        диалог.grab_set()
        диалог.focus_set()

    def _создать_интерфейс(self) -> None:
        основной = ttk.Frame(self.окно, padding=24)
        основной.pack(fill="both", expand=True)
        основной.columnconfigure(0, weight=1)
        основной.rowconfigure(2, weight=1)
        шапка = ttk.Frame(основной)
        шапка.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        шапка.columnconfigure(0, weight=1)
        self._надпись(шапка, "Документы", размер=25, жирный=True, фон=ФОН).grid(
            row=0, column=0, sticky="w")
        self._надпись(шапка, "Документы → редактируемый текст", цвет=ВТОРИЧНЫЙ, фон=ФОН).grid(
            row=1, column=0, sticky="w", pady=(4, 0))
        self._кнопка(шапка, "Оформление", self._настроить_оформление).grid(
            row=0, column=1, rowspan=2, padx=(12, 10))
        self.кнопка_стоп = self._кнопка(шапка, "Остановить", self._остановить)
        self.кнопка_стоп.grid(row=0, column=2, rowspan=2, padx=(0, 10))
        self.кнопка_стоп.grid_remove()
        self.кнопка_распознать = self._кнопка(
            шапка, "Распознать комплект", self._начать_распознавание, акцент=True, state="disabled")
        self.кнопка_распознать.grid(row=0, column=3, rowspan=2)

        панель = ttk.Frame(основной)
        панель.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        панель.columnconfigure(1, weight=1)
        self.кнопка_параметров = self._кнопка(панель, "Параметры  ▾", self._открыть_параметры)
        self.кнопка_параметров.grid(row=0, column=0, sticky="w")
        self.сводка_параметров = self._надпись(панель, размер=10, цвет=ВТОРИЧНЫЙ, фон=ФОН)
        self.сводка_параметров.grid(row=0, column=1, sticky="w", padx=16)
        self.меню_параметров = self._новое_меню(self.окно)
        for текст, переменная in (("Проверить текст после распознавания", self.проверка),
                                  ("Шаблон ЮФУ — только раздел «Диплом»", self.диплом),
                                  ("Сверять документы комплекта", self.сверка)):
            self.меню_параметров.add_checkbutton(label=текст, variable=переменная,
                                                command=self._обновить_параметры)
        self._обновить_параметры()
        self.итог_файлов = self._надпись(панель, размер=11, жирный=True, фон=ФОН)
        self.итог_файлов.grid(row=0, column=2, sticky="e")
        рабочая = ttk.Panedwindow(основной, orient="vertical")
        рабочая.grid(row=2, column=0, sticky="nsew")
        self._создать_панель_файлов(рабочая)
        self._создать_панель_результата(рабочая)
        нижняя = ttk.Frame(основной)
        нижняя.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        нижняя.columnconfigure(0, weight=1)
        self.статус = self._надпись(нижняя, "Выберите раздел и добавьте фото или PDF.",
                                   размер=11, цвет=ВТОРИЧНЫЙ, фон=ФОН, wraplength=800)
        self.статус.grid(row=0, column=0, sticky="w")
        нижняя.bind("<Configure>", lambda событие: self.статус.configure(
            wraplength=max(250, событие.width - 180)))
        self.прогресс = Прогресс(нижняя, палитра=self.оформление.палитра)
        self._компоненты.append(self.прогресс)
        self.прогресс.grid(row=0, column=1, sticky="e", padx=(20, 0))

    def _открыть_параметры(self):
        if not self.занято:
            self._показать_меню(self.кнопка_параметров, self.меню_параметров)

    def _обновить_параметры(self):
        включены = []
        if self.проверка.get():
            включены.append("Проверка текста")
        if self.диплом.get():
            включены.append("Шаблон ЮФУ: диплом")
        if self.сверка.get():
            включены.append("Сверка")
        self.сводка_параметров.configure(text=" · ".join(включены) or "Обычное распознавание")

    def _создать_панель_файлов(self, родитель) -> None:
        оболочка = self._карточка(родитель, height=320)
        родитель.add(оболочка, weight=1)
        карточка = оболочка.body
        карточка.columnconfigure(0, weight=1)
        карточка.rowconfigure(3, weight=1)
        шапка = ttk.Frame(карточка, style="Card.TFrame")
        шапка.grid(row=0, column=0, sticky="ew")
        шапка.columnconfigure(1, weight=1)
        self.выбранный_раздел = tk.StringVar(value=self.раздел)
        self.меню_разделов = self._новое_меню(self.окно)
        self.кнопка_раздела = self._кнопка(шапка, "Диплом  ▾", lambda: self._показать_меню(
            self.кнопка_раздела, self.меню_разделов), фон=ПОВЕРХНОСТЬ)
        self.кнопка_раздела.grid(row=0, column=0, sticky="w")
        self.поддержка_форматов = self._надпись(шапка, размер=10, цвет=ВТОРИЧНЫЙ)
        self.поддержка_форматов.grid(row=0, column=1, sticky="e")
        self.описание_раздела = self._надпись(карточка, размер=11, цвет=ВТОРИЧНЫЙ, wraplength=900)
        self.описание_раздела.grid(row=1, column=0, sticky="ew", pady=(8, 12))
        панель = ttk.Frame(карточка, style="Card.TFrame")
        панель.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        self.кнопка_добавить = self._кнопка(панель, "+ Добавить файлы", self._добавить_файлы,
                                          фон=ПОВЕРХНОСТЬ)
        self.кнопка_добавить.pack(side="left")
        self.кнопка_удалить = self._кнопка(панель, "Удалить", self._удалить_файлы, фон=ПОВЕРХНОСТЬ)
        self.кнопка_удалить.pack(side="left", padx=(8, 0))
        self.кнопка_выше = self._кнопка(панель, "↑ Выше", lambda: self._переместить(-1), фон=ПОВЕРХНОСТЬ)
        self.кнопка_выше.pack(side="left", padx=(8, 0))
        self.кнопка_ниже = self._кнопка(панель, "↓ Ниже", lambda: self._переместить(1), фон=ПОВЕРХНОСТЬ)
        self.кнопка_ниже.pack(side="left", padx=(8, 0))
        оболочка_списка = self._карточка(карточка, фон=ПОВЕРХНОСТЬ, цвет="field", отступ=10, height=100)
        оболочка_списка.grid(row=3, column=0, sticky="nsew")
        список = оболочка_списка.body
        список.rowconfigure(0, weight=1)
        список.columnconfigure(0, weight=1)
        self.список = ttk.Treeview(список, columns=("номер", "файл", "формат"),
                                 show="headings", selectmode="extended", height=3)
        for код, текст, ширина in (("номер", "№", 42), ("файл", "Файл", 330),
                                    ("формат", "Формат", 160)):
            self.список.heading(код, text=текст, anchor="w")
            self.список.column(код, width=ширина, minwidth=ширина if код != "файл" else 160,
                               stretch=код == "файл", anchor="w")
        self.список.grid(row=0, column=0, sticky="nsew")
        полоса = self._полоса(список, self.список.yview)
        полоса.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.список.configure(yscrollcommand=полоса.set)
        self.список.bind("<<TreeviewSelect>>", lambda событие: self._обновить_кнопки())
        for клавиша in ("<Delete>", "<BackSpace>"):
            self.список.bind(клавиша, lambda событие: self._удалить_файлы())
        self.подсказка_файлов = self._надпись(
            карточка, "Можно добавить несколько файлов. Все страницы PDF обрабатываются автоматически.",
            размер=10, цвет=ВТОРИЧНЫЙ, wraplength=900)
        self.подсказка_файлов.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        карточка.bind("<Configure>", lambda e: (
            self.описание_раздела.configure(wraplength=max(200, e.width)),
            self.подсказка_файлов.configure(wraplength=max(200, e.width))))

    def _создать_панель_результата(self, родитель) -> None:
        оболочка = self._карточка(родитель, height=310)
        родитель.add(оболочка, weight=2)
        карточка = оболочка.body
        карточка.columnconfigure(0, weight=1)
        карточка.rowconfigure(1, weight=1)
        шапка = ttk.Frame(карточка, style="Card.TFrame")
        шапка.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        шапка.columnconfigure(0, weight=1)
        self._надпись(шапка, "Распознанный текст", размер=16, жирный=True).grid(
            row=0, column=0, sticky="w")
        self.счётчик_текста = self._надпись(шапка, "Весь комплект", размер=10, цвет=ВТОРИЧНЫЙ)
        self.счётчик_текста.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.кнопка_копировать = self._кнопка(шапка, "Копировать", self._копировать,
                                            фон=ПОВЕРХНОСТЬ, state="disabled")
        self.кнопка_копировать.grid(row=0, column=1, rowspan=2, padx=(8, 0))
        self.кнопка_сохранить = self._кнопка(шапка, "Сохранить TXT…", self._сохранить,
                                           фон=ПОВЕРХНОСТЬ, state="disabled")
        self.кнопка_сохранить.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        оболочка_поля = self._карточка(карточка, фон=ПОВЕРХНОСТЬ, цвет="field", отступ=12, height=160)
        оболочка_поля.grid(row=1, column=0, sticky="nsew")
        поле = оболочка_поля.body
        поле.columnconfigure(0, weight=1)
        поле.rowconfigure(0, weight=1)
        п = self.оформление.палитра
        self.результат = tk.Text(поле, wrap="word", font=(self.шрифт, self.оформление.шрифт(12)),
                                background=п["field"], foreground=п[ТЕКСТ], insertbackground=п[ТЕКСТ],
                                selectbackground=п["selection"], selectforeground=п[ТЕКСТ],
                                borderwidth=0, highlightthickness=0, padx=3, pady=6,
                                spacing1=2, spacing3=3, height=6, undo=True)
        self.результат.grid(row=0, column=0, sticky="nsew")
        полоса = self._полоса(поле, self.результат.yview)
        полоса.grid(row=0, column=1, sticky="ns", padx=(6, 0))
        self.результат.configure(yscrollcommand=полоса.set)
        self.результат.bind("<<Modified>>", self._текст_изменён)
        self.пустой_результат = self._надпись(
            поле, "Здесь появится текст документов\nЕго можно отредактировать, скопировать или сохранить.",
            размер=12, цвет=ВТОРИЧНЫЙ, фон="field", wraplength=700)
        self.пустой_результат.place(relx=0.5, rely=0.45, anchor="center")
        поле.bind("<Configure>", lambda e: self.пустой_результат.configure(wraplength=max(200, e.width-30)))

    def _выбрать_раздел(self, код: str) -> None:
        self.раздел = код
        тип = self.типы[код]
        self.выбранный_раздел.set(код)
        self.описание_раздела.configure(text=тип.описание)
        self.поддержка_форматов.configure(text=форматы_раздела(код).replace(", ", " / "))
        self.подсказка_файлов.configure(text=(
            "DOCX: текст и таблицы читаются напрямую, без языковой правки. Сканированные страницы добавьте в PDF."
            if код == "curriculum" else
            "Можно добавить несколько файлов. Все страницы PDF обрабатываются автоматически."))
        self._обновить_список()

    def _обновить_список(self, выделить=()) -> None:
        self.список.delete(*self.список.get_children())
        for номер, путь in enumerate(self.файлы[self.раздел]):
            формат = "PDF · все страницы" if путь.suffix.lower() == ".pdf" else путь.suffix[1:].upper()
            self.список.insert("", "end", iid=str(номер), values=(номер + 1, путь.name, формат))
        if выделить:
            self.список.selection_set(tuple(str(номер) for номер in выделить))
            self.список.see(str(min(выделить)))
        self.меню_разделов.delete(0, "end")
        for код, тип in self.типы.items():
            self.меню_разделов.add_radiobutton(
                label=f"{тип.название} · {число_файлов(len(self.файлы[код]))}",
                variable=self.выбранный_раздел, value=код,
                command=lambda к=код: self._выбрать_раздел(к))
        self.кнопка_раздела.configure(
            text=f"{self.типы[self.раздел].название} · {число_файлов(len(self.файлы[self.раздел]))}  ▾")
        всего = sum(map(len, self.файлы.values()))
        self.итог_файлов.configure(text=f"В комплекте: {число_файлов(всего)}")
        self._обновить_кнопки()

    def _обновить_кнопки(self) -> None:
        есть_файлы = any(self.файлы.values())
        выделены = {int(номер) for номер in self.список.selection()}
        количество = len(self.файлы[self.раздел])
        for кнопка, доступна in (
            (self.кнопка_добавить, not self.занято),
            (self.кнопка_удалить, bool(выделены) and not self.занято),
            (self.кнопка_выше, any(i > 0 and i - 1 not in выделены for i in выделены) and not self.занято),
            (self.кнопка_ниже, any(i < количество - 1 and i + 1 not in выделены for i in выделены) and not self.занято),
            (self.кнопка_распознать, есть_файлы and not self.занято),
        ):
            кнопка.configure(state="normal" if доступна else "disabled")
        self.кнопка_параметров.configure(state="disabled" if self.занято else "normal")
        for индекс in range(3):
            self.меню_параметров.entryconfigure(индекс, state="disabled" if self.занято else "normal")

    def _добавить_файлы(self) -> None:
        if self.занято:
            return
        выбранные = filedialog.askopenfilenames(
            parent=self.окно, title=f"{self.типы[self.раздел].название} — добавьте файлы",
            filetypes=типы_файлов(self.раздел), initialdir=str(self.папка_выбора))
        if not выбранные:
            return
        файлы = self.файлы[self.раздел]
        известные = set(файлы)
        новые = []
        отклонены = []
        for имя in выбранные:
            try:
                путь = Path(имя).expanduser().resolve()
            except OSError:
                отклонены.append(Path(имя).name)
                continue
            if путь.suffix.lower() not in расширения_раздела(self.раздел) or not путь.is_file():
                отклонены.append(путь.name)
            elif путь not in известные:
                новые.append(len(файлы))
                файлы.append(путь)
                известные.add(путь)
                self.папка_выбора = путь.parent
        self._обновить_список(новые)
        if новые:
            self._комплект_изменён()
        if отклонены:
            messagebox.showwarning(
                "Некоторые файлы не добавлены",
                f"Для этого раздела поддерживаются доступные файлы: {форматы_раздела(self.раздел)}.\n\n"
                + "\n".join(отклонены[:10]), parent=self.окно)

    def _удалить_файлы(self) -> None:
        if self.занято:
            return
        индексы = sorted((int(i) for i in self.список.selection()), reverse=True)
        for индекс in индексы:
            del self.файлы[self.раздел][индекс]
        self._обновить_список()
        if индексы:
            self._комплект_изменён()

    def _переместить(self, направление: int) -> None:
        if self.занято:
            return
        файлы = self.файлы[self.раздел]
        выделены = {int(i) for i in self.список.selection()}
        индексы = sorted(выделены, reverse=направление > 0)
        for индекс in индексы:
            сосед = индекс + направление
            if 0 <= сосед < len(файлы) and сосед not in выделены:
                файлы[индекс], файлы[сосед] = файлы[сосед], файлы[индекс]
                выделены.remove(индекс)
                выделены.add(сосед)
        self._обновить_список(выделены)
        if индексы:
            self._комплект_изменён()

    def _комплект_изменён(self) -> None:
        self.статус.configure(text="Комплект готов. Нажмите «Распознать комплект».")
        if self._число_символов:
            self.счётчик_текста.configure(text="Комплект изменён · показан предыдущий результат")

    def _начать_распознавание(self) -> None:
        if self.занято:
            return
        задания = tuple(Задание(тип.код, путь)
                        for тип in ТИПЫ_ДОКУМЕНТОВ for путь in self.файлы[тип.код])
        if not задания:
            return
        self.занято = True
        self.остановка.clear()
        self.результаты.clear()
        self.отчёт_сверки = ""
        self._очистить_текст()
        self.прогресс.configure(maximum=len(задания), value=0)
        self.статус.configure(text="Подготавливаю распознавание…")
        self.кнопка_стоп.configure(state="normal")
        self.кнопка_стоп.grid()
        self._обновить_кнопки()
        threading.Thread(target=self._распознать_в_фоне,
                         args=(задания, self.проверка.get(), self.диплом.get(), self.сверка.get()),
                         daemon=True).start()
        self.окно.after(100, self._проверить_очередь)

    def _распознать_в_фоне(self, задания: tuple[Задание, ...], проверять: bool,
                          шаблон_диплома: bool, сверять: bool = True) -> None:
        обработанные = []
        try:
            for номер, задание in enumerate(задания, start=1):
                if self.остановка.is_set():
                    break

                def прогресс(сообщение: str) -> None:
                    if not self.остановка.is_set():
                        self.очередь.put(("статус", f"Файл {номер} из {len(задания)} · {задание.путь.name}\n{сообщение}"))

                try:
                    текст = self.сеанс.обработать(задание, проверять=проверять,
                                                 шаблон_диплома=шаблон_диплома, прогресс=прогресс)
                    результат = РезультатФайла(задание, текст=текст,
                                               исправления=self.сеанс.последние_правки,
                                               исходный_текст=self.сеанс.исходный_текст)
                except Exception as ошибка:
                    результат = РезультатФайла(задание, ошибка=str(ошибка))
                обработанные.append(результат)
                self.очередь.put(("результат", (номер, результат)))
            if сверять and обработанные:
                self.очередь.put(("статус", "Сопоставляю документы комплекта…"))
                try:
                    from document_review import сверить_комплект
                    записи, отчёт = сверить_комплект(обработанные, неполный=self.остановка.is_set())
                except Exception as ошибка:
                    записи, отчёт = обработанные, f"СВЕРКА КОМПЛЕКТА\nНе удалось выполнить сверку: {ошибка}. Результаты файлов сохранены."
                self.очередь.put(("сверка", (записи, отчёт)))
        finally:
            self.очередь.put(("завершено", (self.остановка.is_set(), len(задания))))

    def _проверить_очередь(self) -> None:
        while True:
            try:
                тип, данные = self.очередь.get_nowait()
            except queue.Empty:
                break
            if тип == "статус":
                if not self.остановка.is_set():
                    self.статус.configure(text=данные)
            elif тип == "результат":
                номер, результат = данные
                self.прогресс.configure(value=номер)
                self._добавить_результат(результат)
            elif тип == "сверка":
                self.результаты, self.отчёт_сверки = данные
                текст = собрать_результаты(self.результаты) + "\n\n" + self.отчёт_сверки
                self.результат.configure(state="normal")
                self.результат.delete("1.0", tk.END)
                self.результат.insert("1.0", текст)
                self.результат.edit_reset()
                self.результат.edit_modified(False)
                self.результат.configure(state="disabled")
                self._число_символов = len(текст)
                self._обновить_экспорт()
            elif тип == "завершено":
                self.занято = False
                остановлено, всего = данные
                self.результат.configure(state="normal")
                self.результат.edit_modified(False)
                self.кнопка_стоп.grid_remove()
                self._обновить_кнопки()
                успешных = sum(bool(р.текст.strip()) for р in self.результаты)
                ошибок = len(self.результаты) - успешных
                if остановлено:
                    сообщение = f"Остановлено. Обработано файлов: {len(self.результаты)} из {всего}."
                elif ошибок:
                    сообщение = f"Готово файлов: {успешных}. С ошибками: {ошибок} — подробности в результате."
                else:
                    сообщение = f"Готово · {число_файлов(успешных)}. Текст можно отредактировать и сохранить."
                if self.отчёт_сверки:
                    сообщение += " Отчёт сверки — в конце текста."
                self.статус.configure(text=сообщение)
        if self.занято:
            self.окно.after(100, self._проверить_очередь)

    def _остановить(self) -> None:
        if self.занято:
            self.остановка.set()
            self.кнопка_стоп.configure(state="disabled")
            self.статус.configure(text="Остановлю после текущего файла. Его страницы и готовые результаты сохранятся в окне.")

    def _очистить_текст(self) -> None:
        self.результат.configure(state="normal")
        self.результат.delete("1.0", tk.END)
        self.результат.edit_reset()
        self.результат.edit_modified(False)
        self.результат.configure(state="disabled")
        self._число_символов = 0
        self._обновить_экспорт()

    def _добавить_результат(self, результат: РезультатФайла) -> None:
        новый_раздел = (
            not self.результаты
            or self.результаты[-1].задание.категория != результат.задание.категория
        )
        текст = ("\n\n" if self.результаты else "") + собрать_результаты(
            (результат,), заголовки_разделов=новый_раздел
        )
        self.результаты.append(результат)
        self.результат.configure(state="normal")
        self.результат.insert(tk.END, текст)
        # В историю отмены попадают только ручные правки после распознавания.
        self.результат.edit_reset()
        self.результат.edit_modified(False)
        self.результат.configure(state="disabled" if self.занято else "normal")
        self._число_символов += len(текст)
        self._обновить_экспорт()

    def _текст_изменён(self, событие=None) -> None:
        if self.результат.edit_modified():
            self.результат.edit_modified(False)
            self._число_символов = (self.результат.count("1.0", "end-1c", "chars") or (0,))[0]
            self._обновить_экспорт()

    def _обновить_экспорт(self) -> None:
        есть_текст = self._число_символов > 0
        for кнопка in (self.кнопка_копировать, self.кнопка_сохранить):
            кнопка.configure(state="normal" if есть_текст else "disabled")
        self.счётчик_текста.configure(text=f"Символов: {self._число_символов:,}".replace(",", " ") if есть_текст else "Весь комплект")
        if есть_текст:
            self.пустой_результат.place_forget()
        else:
            self.пустой_результат.place(relx=0.5, rely=0.45, anchor="center")

    def _получить_текст(self) -> str:
        return self.результат.get("1.0", "end-1c")

    def _копировать(self) -> None:
        текст = self._получить_текст()
        if текст.strip():
            self.окно.clipboard_clear()
            self.окно.clipboard_append(текст)
            if not self.занято:
                self.статус.configure(text="Текст скопирован в буфер обмена.")

    def _сохранить(self) -> None:
        текст = self._получить_текст()
        if not текст.strip():
            return
        путь = filedialog.asksaveasfilename(
            parent=self.окно, title="Сохранить текст документов", defaultextension=".txt",
            initialfile="documents_result.txt", filetypes=(("Текстовый файл", "*.txt"),))
        if not путь:
            return
        try:
            Path(путь).write_text(текст + "\n", encoding="utf-8")
        except OSError as ошибка:
            messagebox.showerror("Не удалось сохранить файл", str(ошибка), parent=self.окно)
            return
        if not self.занято:
            self.статус.configure(text=f"Сохранено: {Path(путь).name}")

    def _закрыть(self) -> None:
        if self.занято and not messagebox.askyesno(
            "Распознавание выполняется", "Закрыть окно до завершения распознавания?",
            parent=self.окно,
        ):
            return
        self.остановка.set()
        self.окно.destroy()


def main() -> None:
    окно = tk.Tk()
    ПриложениеOCR(окно)
    окно.mainloop()


if __name__ == "__main__":
    main()
