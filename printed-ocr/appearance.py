"""Палитры интерфейса и сохранение пользовательского оформления без Tk/OCR."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile


ПУТЬ_НАСТРОЕК = Path.home() / "Library/Application Support/PrintedOCR/appearance.json"
ТЕМЫ = {
    "Тёмная": {
        "background": "#111827", "surface": "#1C2636", "text": "#EDF2FA",
        "muted": "#AAB8CD", "border": "#39475D", "hover": "#2B3950",
        "disabled": "#8391A7", "selection": "#35465F",
    },
    "Графитовая": {
        "background": "#18181B", "surface": "#242428", "text": "#F4F4F5",
        "muted": "#B4B4BF", "border": "#45454F", "hover": "#36363F",
        "disabled": "#92929E", "selection": "#454552",
    },
    "Светлая": {
        "background": "#F1F4F8", "surface": "#FFFFFF", "text": "#18263C",
        "muted": "#526179", "border": "#CBD5E1", "hover": "#E7EDF5",
        "disabled": "#6B778A", "selection": "#DBE5F3",
    },
}
# Пары: обычная кнопка и наведение; белый текст читается на обоих цветах.
АКЦЕНТЫ = {
    "Синий": ("#2563EB", "#1D4ED8"),
    "Фиолетовый": ("#7C3AED", "#6D28D9"),
    "Бирюзовый": ("#0F766E", "#115E59"),
    "Розовый": ("#BE185D", "#9D174D"),
}
РАЗМЕРЫ = {"Компактный": 0, "Обычный": 1, "Крупный": 2}


@dataclass(frozen=True)
class Оформление:
    тема: str = "Тёмная"
    акцент: str = "Синий"
    размер: str = "Обычный"

    def __post_init__(self) -> None:
        for значение, варианты in ((self.тема, ТЕМЫ), (self.акцент, АКЦЕНТЫ),
                                   (self.размер, РАЗМЕРЫ)):
            if not isinstance(значение, str) or значение not in варианты:
                raise ValueError("Неизвестный вариант оформления")

    @property
    def палитра(self) -> dict[str, str]:
        акцент, наведение = АКЦЕНТЫ[self.акцент]
        return {**ТЕМЫ[self.тема], "accent": акцент, "accent_hover": наведение}

    def шрифт(self, размер: int) -> int:
        return размер + РАЗМЕРЫ[self.размер]


def загрузить_оформление(путь: Path = ПУТЬ_НАСТРОЕК) -> Оформление:
    try:
        данные = json.loads(путь.read_text(encoding="utf-8"))
        if not isinstance(данные, dict):
            return Оформление()
        # Неизвестные и повреждённые поля не мешают использовать остальные.
        значения = {}
        for ключ, варианты in (("тема", ТЕМЫ), ("акцент", АКЦЕНТЫ), ("размер", РАЗМЕРЫ)):
            значение = данные.get(ключ)
            if isinstance(значение, str) and значение in варианты:
                значения[ключ] = значение
        return Оформление(**значения)
    except (OSError, ValueError):
        return Оформление()


def сохранить_оформление(настройки: Оформление, путь: Path = ПУТЬ_НАСТРОЕК) -> None:
    """Атомарная запись: прерванное сохранение не портит предыдущие настройки."""
    путь.parent.mkdir(parents=True, exist_ok=True)
    временный = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=путь.parent,
                                prefix=".appearance-", delete=False) as файл:
            временный = Path(файл.name)
            json.dump(asdict(настройки), файл, ensure_ascii=False, indent=2)
            файл.write("\n")
        временный.replace(путь)
    finally:
        if временный is not None:
            временный.unlink(missing_ok=True)
