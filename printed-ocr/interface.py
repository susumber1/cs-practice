"""Оконное приложение для распознавания комплектов документов."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from document_batch import (
    ДОПУСТИМЫЕ_РАСШИРЕНИЯ,
    ТИПЫ_ДОКУМЕНТОВ,
    Задание,
    РезультатФайла,
    СеансРаспознавания,
    собрать_результаты,
)


ТИПЫ_ФАЙЛОВ = (
    ("Фото и PDF", tuple(
        шаблон
        for расширение in sorted(ДОПУСТИМЫЕ_РАСШИРЕНИЯ)
        for шаблон in (f"*{расширение}", f"*{расширение.upper()}")
    )),
    ("Все файлы", "*"),
)
ФОН = "#F3F6FA"
БЕЛЫЙ = "#FFFFFF"
ТЕКСТ = "#18263C"
ВТОРИЧНЫЙ = "#66768C"
АКЦЕНТ = "#2563EB"
ГРАНИЦА = "#DEE5EF"


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
        окно.configure(background=ФОН)
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
        self.проверка = tk.BooleanVar(value=False)
        self.диплом = tk.BooleanVar(value=False)
        self.папка_выбора = Path.home()
        self._стили()
        self._создать_интерфейс()
        self._выбрать_раздел(self.раздел)
        окно.protocol("WM_DELETE_WINDOW", self._закрыть)
        for сочетание in ("<Command-o>", "<Control-o>"):
            окно.bind(сочетание, lambda событие: self._добавить_файлы())

    def _стили(self) -> None:
        стиль = ttk.Style(self.окно)
        стиль.theme_use("clam")
        стиль.configure("TFrame", background=ФОН)
        стиль.configure("Card.TFrame", background=БЕЛЫЙ)
        стиль.configure("TLabel", background=ФОН, foreground=ТЕКСТ,
                         font=(self.шрифт, 12))
        стиль.configure("TButton", background=БЕЛЫЙ, foreground=ТЕКСТ,
                         bordercolor=ГРАНИЦА, lightcolor=БЕЛЫЙ, darkcolor=ГРАНИЦА,
                         padding=(12, 8), font=(self.шрифт, 11), relief="flat")
        стиль.map("TButton", background=[("active", "#EDF2FA")],
                    foreground=[("disabled", "#9AA6B6")])
        стиль.configure("Accent.TButton", background=АКЦЕНТ, foreground=БЕЛЫЙ,
                         borderwidth=0, padding=(18, 11),
                         font=(self.шрифт, 12, "bold"))
        стиль.map("Accent.TButton", background=[("disabled", "#DFE7F3"),
                                                  ("active", "#1D4ED8")],
                    foreground=[("disabled", "#7B8CA6")])
        стиль.configure("Nav.TButton", background=ФОН, borderwidth=0,
                         padding=(14, 13), anchor="w", font=(self.шрифт, 12))
        стиль.configure("Selected.Nav.TButton", background="#E3EDFF",
                         foreground="#1D4ED8", font=(self.шрифт, 12, "bold"))
        стиль.map("Selected.Nav.TButton", background=[("active", "#D7E5FF")])
        стиль.configure("TCheckbutton", background=ФОН, foreground=ТЕКСТ,
                         font=(self.шрифт, 11), padding=(0, 3))
        стиль.map("TCheckbutton", background=[("active", ФОН)])
        стиль.configure("Treeview", background=БЕЛЫЙ, fieldbackground=БЕЛЫЙ,
                         foreground=ТЕКСТ, rowheight=31, borderwidth=0,
                         font=(self.шрифт, 11))
        стиль.configure("Treeview.Heading", background="#F5F8FC",
                         foreground=ВТОРИЧНЫЙ, relief="flat", padding=(8, 7),
                         font=(self.шрифт, 10, "bold"))
        стиль.map("Treeview", background=[("selected", "#DFEAFF")],
                    foreground=[("selected", "#173F8B")])
        стиль.configure("Horizontal.TProgressbar", troughcolor="#E4EAF3",
                         background=АКЦЕНТ, borderwidth=0, thickness=5)
        стиль.configure("TPanedwindow", background=ФОН)

    def _надпись(self, родитель, текст="", *, размер=12, жирный=False,
                 цвет=ТЕКСТ, фон=БЕЛЫЙ, **параметры) -> tk.Label:
        return tk.Label(родитель, text=текст, background=фон, foreground=цвет,
                        font=(self.шрифт, размер, "bold" if жирный else "normal"),
                        anchor="w", justify="left", **параметры)

    def _создать_интерфейс(self) -> None:
        основной = ttk.Frame(self.окно, padding=22)
        основной.pack(fill="both", expand=True)
        основной.columnconfigure(0, weight=1)
        основной.rowconfigure(2, weight=1)
        шапка = ttk.Frame(основной)
        шапка.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        шапка.columnconfigure(0, weight=1)
        self._надпись(шапка, "Документы", размер=25, жирный=True, фон=ФОН).grid(
            row=0, column=0, sticky="w")
        self._надпись(шапка, "Соберите комплект и получите текст по разделам",
                      цвет=ВТОРИЧНЫЙ, фон=ФОН).grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.кнопка_стоп = ttk.Button(шапка, text="Остановить", command=self._остановить)
        self.кнопка_стоп.grid(row=0, column=1, rowspan=2, padx=(8, 10))
        self.кнопка_стоп.grid_remove()
        self.кнопка_распознать = ttk.Button(
            шапка, text="Распознать комплект", style="Accent.TButton",
            command=self._начать_распознавание, state="disabled")
        self.кнопка_распознать.grid(row=0, column=2, rowspan=2)

        параметры = ttk.Frame(основной)
        параметры.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        self.флажок_проверки = ttk.Checkbutton(
            параметры, text="Проверить текст после распознавания", variable=self.проверка)
        self.флажок_проверки.grid(row=0, column=0, sticky="w", padx=(0, 24))
        self.флажок_диплома = ttk.Checkbutton(
            параметры, text="Диплом ЮФУ по шаблону", variable=self.диплом)
        self.флажок_диплома.grid(row=0, column=1, sticky="w")
        self._надпись(
            параметры, "Шаблон — только для диплома. Паспортные данные сохраняются без языковой правки.",
            размер=10, цвет=ВТОРИЧНЫЙ, фон=ФОН,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))

        содержимое = ttk.Frame(основной)
        содержимое.grid(row=2, column=0, sticky="nsew")
        содержимое.columnconfigure(1, weight=1)
        содержимое.rowconfigure(0, weight=1)
        боковая = ttk.Frame(содержимое, width=238)
        боковая.grid(row=0, column=0, sticky="nsw", padx=(0, 20))
        боковая.grid_propagate(False)
        боковая.columnconfigure(0, weight=1)
        self._надпись(боковая, "КОМПЛЕКТ ДОКУМЕНТОВ", размер=10, жирный=True,
                      цвет=ВТОРИЧНЫЙ, фон=ФОН).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.кнопки_разделов = {}
        for номер, тип in enumerate(ТИПЫ_ДОКУМЕНТОВ, start=1):
            кнопка = ttk.Button(боковая, style="Nav.TButton",
                                command=lambda код=тип.код: self._выбрать_раздел(код))
            кнопка.grid(row=номер, column=0, sticky="ew", pady=(0, 5))
            self.кнопки_разделов[тип.код] = кнопка
        боковая.rowconfigure(6, weight=1)
        self.итог_файлов = self._надпись(боковая, размер=11, жирный=True, фон=ФОН)
        self.итог_файлов.grid(row=7, column=0, sticky="w", pady=(20, 5))
        self._надпись(боковая, "JPG, JPEG, PNG, HEIC, PDF\nВсе страницы PDF распознаются\nавтоматически.",
                      размер=10, цвет=ВТОРИЧНЫЙ, фон=ФОН).grid(row=8, column=0, sticky="w")

        рабочая = ttk.Panedwindow(содержимое, orient="vertical")
        рабочая.grid(row=0, column=1, sticky="nsew")
        self._создать_панель_файлов(рабочая)
        self._создать_панель_результата(рабочая)
        нижняя = ttk.Frame(основной)
        нижняя.grid(row=3, column=0, sticky="ew", pady=(15, 0))
        нижняя.columnconfigure(0, weight=1)
        self.статус = self._надпись(нижняя, "Добавьте документы в нужные разделы.",
                                   размер=11, цвет=ВТОРИЧНЫЙ, фон=ФОН, wraplength=850)
        self.статус.grid(row=0, column=0, sticky="w")
        нижняя.bind("<Configure>", lambda событие: self.статус.configure(
            wraplength=max(250, событие.width - 170)))
        self.прогресс = ttk.Progressbar(нижняя, length=150, mode="determinate")
        self.прогресс.grid(row=0, column=1, sticky="e", padx=(15, 0))

    def _создать_панель_файлов(self, родитель) -> None:
        карточка = ttk.Frame(родитель, style="Card.TFrame", padding=18)
        родитель.add(карточка, weight=1)
        карточка.columnconfigure(0, weight=1)
        карточка.rowconfigure(3, weight=1)
        self.заголовок_раздела = self._надпись(карточка, размер=17, жирный=True)
        self.заголовок_раздела.grid(row=0, column=0, sticky="w")
        self.описание_раздела = self._надпись(карточка, размер=11, цвет=ВТОРИЧНЫЙ,
                                           wraplength=650)
        self.описание_раздела.grid(row=1, column=0, sticky="ew", pady=(5, 12))
        панель = ttk.Frame(карточка, style="Card.TFrame")
        панель.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        self.кнопка_добавить = ttk.Button(панель, text="+ Добавить фото или PDF",
                                        command=self._добавить_файлы)
        self.кнопка_добавить.pack(side="left")
        self.кнопка_удалить = ttk.Button(панель, text="Удалить", command=self._удалить_файлы)
        self.кнопка_удалить.pack(side="left", padx=(8, 0))
        self.кнопка_выше = ttk.Button(панель, text="Выше", command=lambda: self._переместить(-1))
        self.кнопка_выше.pack(side="left", padx=(8, 0))
        self.кнопка_ниже = ttk.Button(панель, text="Ниже", command=lambda: self._переместить(1))
        self.кнопка_ниже.pack(side="left", padx=(8, 0))
        список = ttk.Frame(карточка, style="Card.TFrame")
        список.grid(row=3, column=0, sticky="nsew")
        список.rowconfigure(0, weight=1)
        список.columnconfigure(0, weight=1)
        self.список = ttk.Treeview(список, columns=("номер", "файл", "формат"),
                                 show="headings", selectmode="extended", height=4)
        for код, текст, ширина in (("номер", "№", 42), ("файл", "Файл", 330),
                                    ("формат", "Формат", 145)):
            self.список.heading(код, text=текст, anchor="w")
            self.список.column(код, width=ширина, minwidth=ширина if код != "файл" else 160,
                               stretch=код == "файл", anchor="w")
        self.список.grid(row=0, column=0, sticky="nsew")
        полоса = ttk.Scrollbar(список, orient="vertical", command=self.список.yview)
        полоса.grid(row=0, column=1, sticky="ns")
        self.список.configure(yscrollcommand=полоса.set)
        self.список.bind("<<TreeviewSelect>>", lambda событие: self._обновить_кнопки())
        for клавиша in ("<Delete>", "<BackSpace>"):
            self.список.bind(клавиша, lambda событие: self._удалить_файлы())
        self.подсказка_файлов = self._надпись(
            карточка, "Можно выбрать несколько файлов сразу. Порядок задаётся кнопками «Выше» и «Ниже».",
            размер=10, цвет=ВТОРИЧНЫЙ, wraplength=650)
        self.подсказка_файлов.grid(row=4, column=0, sticky="ew", pady=(9, 0))

    def _создать_панель_результата(self, родитель) -> None:
        карточка = ttk.Frame(родитель, style="Card.TFrame", padding=18)
        родитель.add(карточка, weight=2)
        карточка.columnconfigure(0, weight=1)
        карточка.rowconfigure(1, weight=1)
        шапка = ttk.Frame(карточка, style="Card.TFrame")
        шапка.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        шапка.columnconfigure(0, weight=1)
        self._надпись(шапка, "Распознанный текст", размер=16, жирный=True).grid(
            row=0, column=0, sticky="w")
        self.счётчик_текста = self._надпись(шапка, "Весь комплект", размер=10, цвет=ВТОРИЧНЫЙ)
        self.счётчик_текста.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.кнопка_копировать = ttk.Button(шапка, text="Копировать", command=self._копировать,
                                           state="disabled")
        self.кнопка_копировать.grid(row=0, column=1, rowspan=2, padx=(8, 0))
        self.кнопка_сохранить = ttk.Button(шапка, text="Сохранить TXT…", command=self._сохранить,
                                          state="disabled")
        self.кнопка_сохранить.grid(row=0, column=2, rowspan=2, padx=(8, 0))
        поле = ttk.Frame(карточка, style="Card.TFrame")
        поле.grid(row=1, column=0, sticky="nsew")
        поле.columnconfigure(0, weight=1)
        поле.rowconfigure(0, weight=1)
        self.результат = ScrolledText(поле, wrap="word", font=(self.шрифт, 12),
                                    background=БЕЛЫЙ, foreground=ТЕКСТ, insertbackground=АКЦЕНТ,
                                    selectbackground="#DFEAFF", selectforeground=ТЕКСТ,
                                    borderwidth=0, highlightthickness=0, padx=3, pady=6,
                                    spacing1=2, spacing3=3, height=10, undo=True)
        self.результат.grid(row=0, column=0, sticky="nsew")
        self.результат.bind("<<Modified>>", self._текст_изменён)
        self.пустой_результат = self._надпись(
            поле, "Здесь появится текст документов\nПосле распознавания его можно отредактировать и сохранить.",
            размер=12, цвет=ВТОРИЧНЫЙ)
        self.пустой_результат.place(relx=0.5, rely=0.45, anchor="center")

    def _выбрать_раздел(self, код: str) -> None:
        self.раздел = код
        тип = self.типы[код]
        self.заголовок_раздела.configure(text=тип.название)
        self.описание_раздела.configure(text=тип.описание)
        self._обновить_список()

    def _обновить_список(self, выделить=()) -> None:
        self.список.delete(*self.список.get_children())
        for номер, путь in enumerate(self.файлы[self.раздел]):
            формат = "PDF · все страницы" if путь.suffix.lower() == ".pdf" else путь.suffix[1:].upper()
            self.список.insert("", "end", iid=str(номер), values=(номер + 1, путь.name, формат))
        if выделить:
            self.список.selection_set(tuple(str(номер) for номер in выделить))
            self.список.see(str(min(выделить)))
        for код, кнопка in self.кнопки_разделов.items():
            кнопка.configure(text=f"{self.типы[код].название}\n{число_файлов(len(self.файлы[код]))}",
                              style="Selected.Nav.TButton" if код == self.раздел else "Nav.TButton")
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
        for флажок in (self.флажок_диплома, self.флажок_проверки):
            флажок.configure(state="disabled" if self.занято else "normal")

    def _добавить_файлы(self) -> None:
        if self.занято:
            return
        выбранные = filedialog.askopenfilenames(
            parent=self.окно, title=f"{self.типы[self.раздел].название} — добавьте фото или PDF",
            filetypes=ТИПЫ_ФАЙЛОВ, initialdir=str(self.папка_выбора))
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
            if путь.suffix.lower() not in ДОПУСТИМЫЕ_РАСШИРЕНИЯ or not путь.is_file():
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
                "Поддерживаются доступные файлы JPG, JPEG, PNG, HEIC и PDF.\n\n"
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
        self._очистить_текст()
        self.прогресс.configure(maximum=len(задания), value=0)
        self.статус.configure(text="Подготавливаю распознавание…")
        self.кнопка_стоп.configure(state="normal")
        self.кнопка_стоп.grid()
        self._обновить_кнопки()
        threading.Thread(target=self._распознать_в_фоне,
                         args=(задания, self.проверка.get(), self.диплом.get()),
                         daemon=True).start()
        self.окно.after(100, self._проверить_очередь)

    def _распознать_в_фоне(self, задания: tuple[Задание, ...], проверять: bool,
                          шаблон_диплома: bool) -> None:
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
                    результат = РезультатФайла(задание, текст=текст)
                except Exception as ошибка:
                    результат = РезультатФайла(задание, ошибка=str(ошибка))
                self.очередь.put(("результат", (номер, результат)))
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
