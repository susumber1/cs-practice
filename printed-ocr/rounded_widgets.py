"""Небольшие компоненты Tk со скруглениями и без системных рамок."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk


def скругление(холст, x1, y1, x2, y2, радиус, цвет):
    # Рисуем с запасом разрешения: края остаются плавными на Retina.
    w, h = max(1, round(x2-x1)), max(1, round(y2-y1))
    r = max(0, min(радиус, w/2, h/2))
    масштаб = 3
    картинка = Image.new("RGBA", (w*масштаб, h*масштаб))
    ImageDraw.Draw(картинка).rounded_rectangle(
        (0, 0, w*масштаб-1, h*масштаб-1), radius=r*масштаб, fill=цвет)
    фото = ImageTk.PhotoImage(картинка.resize((w, h), Image.Resampling.LANCZOS), master=холст)
    холст._изображения.append(фото)
    return холст.create_image(x1, y1, image=фото, anchor="nw")


class Карточка(tk.Canvas):
    def __init__(self, master, *, палитра, фон="background", цвет="surface", отступ=18,
                 height=200):
        super().__init__(master, bd=0, highlightthickness=0, height=height, width=1)
        self.фон, self.цвет, self.отступ = фон, цвет, отступ
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        self._окно = self.create_window(отступ, отступ, anchor="nw", window=self.body)
        self.bind("<Configure>", self._рисовать)
        self.оформить(палитра)

    def оформить(self, палитра, шрифт=None):
        self.палитра = палитра
        self.configure(background=палитра[self.фон])
        self.body.configure(background=палитра[self.цвет])
        self._рисовать()

    def _рисовать(self, событие=None):
        w, h = self.winfo_width(), self.winfo_height()
        self.delete("форма")
        self._изображения = []
        форма = скругление(self, 0, 0, w, h, 16, self.палитра[self.цвет])
        self.addtag_withtag("форма", форма)
        self.tag_lower(форма)
        self.itemconfigure(self._окно, width=max(1, w-2*self.отступ),
                           height=max(1, h-2*self.отступ))


class Кнопка(tk.Canvas):
    """Кнопка с клавиатурной навигацией; выпадающее меню задаётся через command."""
    def __init__(self, master, *, text, command, палитра, font, фон="background",
                 акцент=False, state="normal", width=None):
        super().__init__(master, bd=0, highlightthickness=0, takefocus=True, cursor="hand2")
        self.текст, self.command, self.фон = text, command, фон
        self.акцент, self.состояние, self.ширина = акцент, state, width
        self._наведение = self._фокус = self._нажата = False
        self.bind("<Configure>", self._рисовать)
        self.bind("<Enter>", lambda e: self._изменить("_наведение", True))
        self.bind("<Leave>", lambda e: self._изменить("_наведение", False))
        self.bind("<FocusIn>", lambda e: self._изменить("_фокус", True))
        self.bind("<FocusOut>", lambda e: self._изменить("_фокус", False))
        self.bind("<ButtonPress-1>", self._нажать)
        self.bind("<ButtonRelease-1>", self._отпустить)
        self.bind("<space>", self._вызвать)
        self.bind("<Return>", self._вызвать)
        self.bind("<Down>", self._вызвать)
        self.оформить(палитра, font)

    def оформить(self, палитра, шрифт):
        self.палитра, self.шрифт = палитра, tkfont.Font(self, font=шрифт)
        super().configure(background=палитра[self.фон])
        self._размер()
        self._рисовать()

    def _размер(self):
        super().configure(width=self.ширина or self.шрифт.measure(self.текст)+32,
                          height=self.шрифт.metrics("linespace")+24,
                          takefocus=self.состояние != "disabled")

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        if "text" in kw:
            self.текст = kw.pop("text")
        if "state" in kw:
            self.состояние = kw.pop("state")
        super().configure(**kw)
        if hasattr(self, "шрифт"):
            self._размер()
            self._рисовать()

    config = configure

    def _изменить(self, имя, значение):
        setattr(self, имя, значение)
        self._рисовать()

    def _нажать(self, событие):
        if self.состояние != "disabled":
            self.focus_set()
            self._изменить("_нажата", True)

    def _отпустить(self, событие):
        нажата = self._нажата
        self._изменить("_нажата", False)
        if нажата and 0 <= событие.x < self.winfo_width() and 0 <= событие.y < self.winfo_height():
            self._вызвать()

    def _вызвать(self, событие=None):
        if self.состояние != "disabled":
            self.command()
        return "break"

    def _рисовать(self, событие=None):
        if not hasattr(self, "палитра"):
            return
        п = self.палитра
        выключена = self.состояние == "disabled"
        цвет = п["hover" if self.фон == "surface" else "surface"]
        текст = п["disabled" if выключена else "text"]
        if self.акцент and not выключена:
            цвет, текст = п["accent_hover" if self._наведение or self._нажата else "accent"], "#FFFFFF"
        elif not выключена and (self._наведение or self._нажата):
            цвет = п["selection"]
        self.delete("all")
        self._изображения = []
        w, h = self.winfo_width(), self.winfo_height()
        if self._фокус and not выключена:
            скругление(self, 0, 0, w, h, 12, п["accent"])
            скругление(self, 2, 2, w-2, h-2, 10, цвет)
        else:
            скругление(self, 0, 0, w, h, 12, цвет)
        self.create_text(w/2, h/2, text=self.текст, font=self.шрифт, fill=текст)


def геометрия_ползунка(высота, начало, конец):
    """Возвращает верх и длину бегунка, включая минимальную область захвата."""
    дорожка = max(1, высота - 8)
    доля = max(0.0, min(1.0, конец - начало))
    длина = min(дорожка, max(28, дорожка * доля))
    ход = дорожка - длина
    верх = 4 + (min(max(начало, 0), 1-доля) / (1-доля) * ход if доля < 1 else 0)
    return верх, длина


class ПолосаПрокрутки(tk.Canvas):
    def __init__(self, master, *, command, палитра, фон="field"):
        super().__init__(master, width=14, bd=0, highlightthickness=0, takefocus=False)
        self.command, self.фон = command, фон
        self.начало, self.конец = 0.0, 1.0
        self._захват = None
        self._наведение = False
        self.bind("<Configure>", self._рисовать)
        self.bind("<Enter>", lambda e: self._подсветить(True))
        self.bind("<Leave>", lambda e: self._подсветить(False))
        self.bind("<Button-1>", self._нажать)
        self.bind("<B1-Motion>", self._тащить)
        self.bind("<ButtonRelease-1>", self._отпустить)
        self.bind("<MouseWheel>", self._колесо)
        self.bind("<Button-4>", lambda e: self.command("scroll", -1, "units"))
        self.bind("<Button-5>", lambda e: self.command("scroll", 1, "units"))
        self.оформить(палитра)

    def оформить(self, палитра, шрифт=None):
        self.палитра = палитра
        self.configure(background=палитра[self.фон])
        self._рисовать()

    def set(self, начало, конец):
        self.начало, self.конец = float(начало), float(конец)
        self._рисовать()

    def _подсветить(self, значение):
        self._наведение = значение
        self._рисовать()

    def _рисовать(self, событие=None):
        self.delete("all")
        self._изображения = []
        if self.конец - self.начало >= 0.999999:
            return
        верх, длина = геометрия_ползунка(self.winfo_height(), self.начало, self.конец)
        цвет = self.палитра["muted" if self._наведение or self._захват is not None else "border"]
        скругление(self, 3, верх, 11, верх+длина, 4, цвет)

    def _нажать(self, событие):
        верх, длина = геометрия_ползунка(self.winfo_height(), self.начало, self.конец)
        if верх <= событие.y <= верх+длина:
            self._захват = событие.y-верх
        else:
            self.command("scroll", -1 if событие.y < верх else 1, "pages")
        self._рисовать()

    def _тащить(self, событие):
        if self._захват is None:
            return
        _, длина = геометрия_ползунка(self.winfo_height(), self.начало, self.конец)
        ход = max(1, self.winfo_height()-8-длина)
        доля = 1-(self.конец-self.начало)
        self.command("moveto", max(0, min(доля, (событие.y-4-self._захват)/ход*доля)))

    def _отпустить(self, событие):
        self._захват = None
        self._рисовать()

    def _колесо(self, событие):
        шаг = -событие.delta
        if self.tk.call("tk", "windowingsystem") != "aqua":
            шаг = int(шаг/120) or (-1 if событие.delta > 0 else 1)
        self.command("scroll", int(шаг), "units")
        return "break"


class Прогресс(tk.Canvas):
    def __init__(self, master, *, палитра):
        super().__init__(master, width=150, height=8, bd=0, highlightthickness=0)
        self.value, self.maximum = 0, 1
        self.bind("<Configure>", self._рисовать)
        self.оформить(палитра)

    def оформить(self, палитра, шрифт=None):
        self.палитра = палитра
        super().configure(background=палитра["background"])
        self._рисовать()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        self.value = kw.pop("value", self.value)
        self.maximum = kw.pop("maximum", self.maximum)
        super().configure(**kw)
        self._рисовать()

    config = configure

    def _рисовать(self, событие=None):
        self.delete("all")
        self._изображения = []
        w, h = self.winfo_width(), self.winfo_height()
        скругление(self, 0, 0, w, h, h/2, self.палитра["surface"])
        доля = min(1, max(0, self.value / max(1, self.maximum)))
        if доля:
            скругление(self, 0, 0, max(h, w*доля), h, h/2, self.палитра["accent"])
