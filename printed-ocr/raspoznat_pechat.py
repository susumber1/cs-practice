"""Распознавание целой страницы печатного текста на русском языке."""

import argparse
import os
from pathlib import Path

import certifi

# У Python.org для macOS сертификаты иногда не настроены. Используем
# актуальный bundle сертификатов, сохраняя настройку пользователя, если она есть.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

import easyocr
import numpy as np
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
import pymupdf


def собрать_строки(результаты) -> list[str]:
    """Группирует найденные фрагменты текста по строкам страницы."""
    фрагменты = []
    for рамка, текст, уверенность in результаты:
        if not текст.strip():
            continue
        координаты = np.asarray(рамка, dtype=float)
        верх = float(np.min(координаты[:, 1]))
        низ = float(np.max(координаты[:, 1]))
        лево = float(np.min(координаты[:, 0]))
        высота = max(1.0, низ - верх)
        фрагменты.append(
            {
                "text": текст.strip(),
                "top": верх,
                "bottom": низ,
                "left": лево,
                "height": высота,
                "confidence": float(уверенность),
            }
        )

    фрагменты.sort(key=lambda ф: ((ф["top"] + ф["bottom"]) / 2, ф["left"]))
    строки: list[dict] = []

    for фрагмент in фрагменты:
        центр = (фрагмент["top"] + фрагмент["bottom"]) / 2
        подходящая_строка = None
        лучшее_расстояние = float("inf")

        for строка in reversed(строки):
            центр_строки = (строка["top"] + строка["bottom"]) / 2
            высота_строки = строка["bottom"] - строка["top"]
            расстояние = abs(центр - центр_строки)
            допуск = 0.55 * max(фрагмент["height"], высота_строки)
            пересечение = max(
                0.0,
                min(фрагмент["bottom"], строка["bottom"])
                - max(фрагмент["top"], строка["top"]),
            )
            доля_пересечения = пересечение / min(
                фрагмент["height"], max(1.0, высота_строки)
            )

            if расстояние <= допуск or доля_пересечения >= 0.35:
                if расстояние < лучшее_расстояние:
                    подходящая_строка = строка
                    лучшее_расстояние = расстояние

        if подходящая_строка is None:
            строки.append(
                {
                    "top": фрагмент["top"],
                    "bottom": фрагмент["bottom"],
                    "parts": [фрагмент],
                }
            )
        else:
            подходящая_строка["top"] = min(
                подходящая_строка["top"], фрагмент["top"]
            )
            подходящая_строка["bottom"] = max(
                подходящая_строка["bottom"], фрагмент["bottom"]
            )
            подходящая_строка["parts"].append(фрагмент)

    строки.sort(key=lambda строка: строка["top"])
    return [
        " ".join(часть["text"] for часть in sorted(строка["parts"], key=lambda ч: ч["left"]))
        for строка in строки
    ]


def распознать_страницу(изображение: Image.Image, распознаватель) -> str:
    """Передаёт одну страницу изображения в OCR-модель."""
    изображение = ImageOps.exif_transpose(изображение).convert("RGB")
    результаты = распознаватель.readtext(
        np.asarray(изображение),
        detail=1,
        paragraph=False,
        batch_size=1,
        min_size=10,
    )
    return "\n".join(собрать_строки(результаты))


def распознать(путь: Path, разворот: bool = False) -> str:
    """Распознаёт изображение или каждую страницу PDF-файла."""
    register_heif_opener()

    # EasyOCR умеет распознавать русский текст и самостоятельно загружает
    # предварительно обученные веса при первом запуске.
    распознаватель = easyocr.Reader(["ru"], gpu=False, verbose=False)

    if путь.suffix.lower() == ".pdf":
        результаты_страниц = []
        with pymupdf.open(str(путь)) as документ:
            if документ.page_count == 0:
                raise ValueError("В PDF нет страниц.")
            for номер, страница in enumerate(документ, start=1):
                пиксели = страница.get_pixmap(
                    matrix=pymupdf.Matrix(1, 1),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                изображение = Image.frombytes(
                    "RGB", (пиксели.width, пиксели.height), пиксели.samples
                )
                if разворот:
                    середина = изображение.width // 2
                    области = [
                        ("левая половина", изображение.crop((0, 0, середина, изображение.height))),
                        (
                            "правая половина",
                            изображение.crop((середина, 0, изображение.width, изображение.height)),
                        ),
                    ]
                else:
                    области = [(None, изображение)]

                for название, область in области:
                    текст = распознать_страницу(область, распознаватель)
                    результаты_страниц.append((номер, название, текст))

        if not any(текст.strip() for _, _, текст in результаты_страниц):
            raise ValueError("На страницах PDF не удалось найти текст.")
        if len(результаты_страниц) == 1 and not разворот:
            return результаты_страниц[0][2]

        размеченные_страницы = []
        for номер, название, текст in результаты_страниц:
            заголовок = f"Страница {номер}"
            if название:
                заголовок += f" — {название}"
            размеченные_страницы.append(
                f"{заголовок}\n{текст}" if текст else заголовок
            )
        return "\n\n".join(размеченные_страницы)

    with Image.open(путь) as исходное_изображение:
        return распознать_страницу(исходное_изображение, распознаватель)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Распознаёт печатный русский текст на фото, скане или в PDF."
    )
    parser.add_argument(
        "файл", type=Path, help="Путь к JPG, PNG, HEIC или PDF"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Файл для результата .txt; если не указан, текст выводится в терминал",
    )
    parser.add_argument(
        "--spread",
        action="store_true",
        help="Разделить каждую страницу PDF на левую и правую половины",
    )
    args = parser.parse_args()

    if not args.файл.is_file():
        parser.error(f"Файл не найден: {args.файл}")
    if args.spread and args.файл.suffix.lower() != ".pdf":
        parser.error("Параметр --spread можно использовать только с PDF-файлом.")

    try:
        текст = распознать(args.файл, разворот=args.spread)
        if not текст.strip():
            raise ValueError("Не удалось найти текст на изображении.")
    except Exception as ошибка:
        parser.exit(1, f"Не удалось обработать файл: {ошибка}\n")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(текст + ("\n" if текст else ""), encoding="utf-8")
        print(f"Текст сохранён в файл: {args.output}")
    else:
        print(текст)


if __name__ == "__main__":
    main()
