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


def распознать(путь: Path) -> str:
    """Загружает русскую OCR-модель и распознаёт страницу целиком."""
    register_heif_opener()
    with Image.open(путь) as исходное_изображение:
        изображение = ImageOps.exif_transpose(исходное_изображение).convert("RGB")

    # EasyOCR умеет распознавать русский текст и самостоятельно загружает
    # предварительно обученные веса при первом запуске.
    распознаватель = easyocr.Reader(["ru"], gpu=False, verbose=False)
    результаты = распознаватель.readtext(
        np.asarray(изображение),
        detail=1,
        paragraph=False,
        batch_size=1,
        min_size=10,
    )
    return "\n".join(собрать_строки(результаты))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Распознаёт страницу печатного русского текста с фото или скана."
    )
    parser.add_argument("изображение", type=Path, help="Путь к файлу JPG, PNG или HEIC")
    parser.add_argument(
        "--output",
        type=Path,
        help="Файл для результата .txt; если не указан, текст выводится в терминал",
    )
    args = parser.parse_args()

    if not args.изображение.is_file():
        parser.error(f"Файл не найден: {args.изображение}")

    try:
        текст = распознать(args.изображение)
    except Exception as ошибка:
        parser.exit(1, f"Не удалось распознать изображение: {ошибка}\n")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(текст + ("\n" if текст else ""), encoding="utf-8")
        print(f"Текст сохранён в файл: {args.output}")
    else:
        print(текст)


if __name__ == "__main__":
    main()
