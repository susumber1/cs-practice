"""Чтение основного текста и таблиц DOCX без Word и дополнительных зависимостей."""

from pathlib import Path
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET


def прочитать_docx(путь: Path) -> str:
    try:
        with ZipFile(путь) as архив:
            часть = архив.getinfo("word/document.xml")
            if часть.file_size > 64 * 1024 * 1024:
                raise ValueError("Текстовая часть DOCX слишком велика (более 64 МБ).")
            документ = ET.fromstring(архив.read(часть))
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError, NotImplementedError) as ошибка:
        raise ValueError("Не удалось прочитать DOCX. Откройте документ в Word и сохраните его заново в .docx.") from ошибка

    пространство = документ.tag.removesuffix("document")
    if пространство not in (
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}",
        "{http://purl.oclc.org/ooxml/wordprocessingml/main}",
    ):
        raise ValueError("Файл не содержит поддерживаемый документ Word (.docx).")
    тег = lambda имя: пространство + имя
    тело = документ.find(тег("body"))
    if тело is None:
        raise ValueError("В DOCX отсутствует основное содержимое документа.")

    есть_текст = False
    есть_изображения = False

    def текст_абзаца(узел):
        nonlocal есть_текст, есть_изображения
        if узел.tag in (тег("del"), тег("moveFrom")):
            return ""  # Удалённые фрагменты исправлений Word не включаем.
        if узел.tag == тег("t"):
            текст = узел.text or ""
            есть_текст |= bool(текст.strip())
            return текст
        if узел.tag == тег("tab"):
            return "\t"
        if узел.tag in (тег("br"), тег("cr")):
            return "\n"
        if узел.tag == тег("noBreakHyphen"):
            return "‑"
        if узел.tag in (тег("drawing"), тег("pict"), тег("object")):
            есть_изображения = True
            return " [Встроенный объект: проверьте изображение или схему в исходном DOCX] "
        return "".join(текст_абзаца(ребёнок) for ребёнок in узел)

    def строки_таблицы(узел):
        # Вложенные таблицы обрабатываются внутри своей ячейки, без дублирования.
        for ребёнок in узел:
            if ребёнок.tag == тег("tr"):
                ячейки = []
                for ячейка in ячейки_строки(ребёнок):
                    ячейки.append(" / ".join(блоки(ячейка)).replace("\n", " / "))
                if any(ячейки):
                    yield " | ".join(ячейки)
            elif ребёнок.tag not in (тег("tbl"), тег("del"), тег("moveFrom")):
                yield from строки_таблицы(ребёнок)

    def ячейки_строки(узел):
        for ребёнок in узел:
            if ребёнок.tag == тег("tc"):
                yield ребёнок
            elif ребёнок.tag not in (тег("del"), тег("moveFrom")):
                yield from ячейки_строки(ребёнок)

    def блоки(узел):
        for ребёнок in узел:
            if ребёнок.tag == тег("p"):
                текст = текст_абзаца(ребёнок).strip()
                if текст:
                    yield текст
            elif ребёнок.tag == тег("tbl"):
                yield from строки_таблицы(ребёнок)
            elif ребёнок.tag not in (тег("del"), тег("moveFrom")):
                yield from блоки(ребёнок)

    текст = "\n".join(блоки(тело))
    if not есть_текст:
        if есть_изображения:
            raise ValueError("В DOCX найдены только изображения или встроенные объекты. Сохраните документ в PDF и добавьте PDF для распознавания.")
        raise ValueError("В основном содержимом DOCX не найден текст.")
    return текст
