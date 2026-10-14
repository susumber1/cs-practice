"""Распознавание русской рукописи по одной строке или по целой странице.

Модель уже обучена заранее. Этот скрипт только загружает её и делает прогноз.
При первом запуске веса модели будут скачаны из Hugging Face.
"""

import argparse
import math
import re
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageFilter, ImageOps
from safetensors.torch import load_file
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    TrOCRProcessor,
    VisionEncoderDecoderModel,
)


# Более крупная модель для распознавания русских рукописных строк.
MODEL_NAME = "Kansallisarkisto/cyrillic-large-handwritten"
# Компактный корректор русской орфографии и пунктуации.
CORRECTOR_NAME = "ai-forever/sage-fredt5-distilled-95m"


class TrOCRProcessorCustom(TrOCRProcessor):
    """Процессор с размерами изображения, заданными в карточке модели."""

    def __init__(self, image_processor, tokenizer):
        self.image_processor = image_processor
        self.tokenizer = tokenizer
        self.current_processor = image_processor
        self.chat_template = None


def выбрать_устройство() -> str:
    """Использует доступный ускоритель, иначе работает на процессоре."""
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def загрузить_распознаватель(использовать_адаптер: bool, устройство: str):
    """Загружает OCR-модель один раз, в том числе для обработки всей страницы."""
    процессор = TrOCRProcessorCustom.from_pretrained(MODEL_NAME)
    модель = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME)
    путь_адаптера = (
        Path(__file__).resolve().parent
        / "handwriting_dataset"
        / "adapter_crossattention.safetensors"
    )
    if использовать_адаптер and путь_адаптера.is_file():
        адаптер = load_file(str(путь_адаптера), device="cpu")
        результат_загрузки = модель.load_state_dict(адаптер, strict=False)
        if результат_загрузки.unexpected_keys:
            raise RuntimeError(
                "Адаптер не совпадает с базовой моделью: "
                + ", ".join(результат_загрузки.unexpected_keys[:5])
            )
        print(f"Используется персональный адаптер: {путь_адаптера}")
    модель.to(устройство)
    модель.eval()  # Режим вывода: ничего не обучаем и не меняем в весах.
    return процессор, модель


def порог_отделения_чернил(яркость: np.ndarray) -> int:
    """Находит порог Отсу и ограничивает его, чтобы не считать бумагу чернилами."""
    гистограмма = np.bincount(яркость.ravel(), minlength=256).astype(np.float64)
    вероятности = гистограмма / гистограмма.sum()
    уровни = np.arange(256, dtype=np.float64)
    накопленная_вероятность = np.cumsum(вероятности)
    накопленная_яркость = np.cumsum(вероятности * уровни)
    общая_яркость = накопленная_яркость[-1]
    знаменатель = накопленная_вероятность * (1.0 - накопленная_вероятность)
    дисперсия = np.zeros(256, dtype=np.float64)
    допустимые = знаменатель > 0
    дисперсия[допустимые] = (
        (общая_яркость * накопленная_вероятность[допустимые]
         - накопленная_яркость[допустимые]) ** 2
        / знаменатель[допустимые]
    )
    return min(int(np.argmax(дисперсия)), 165)


def _сгруппировать_строки(активные_ряды: np.ndarray, допуск: int) -> list[tuple[int, int]]:
    """Собирает соседние строки текста в вертикальные полосы."""
    индексы = np.flatnonzero(активные_ряды)
    if индексы.size == 0:
        return []

    группы: list[tuple[int, int]] = []
    начало = конец = int(индексы[0])
    for индекс in индексы[1:]:
        индекс = int(индекс)
        if индекс - конец - 1 <= допуск:
            конец = индекс
        else:
            группы.append((начало, конец + 1))
            начало = конец = индекс
    группы.append((начало, конец + 1))
    return группы


def выделить_строки_страницы(изображение: Image.Image) -> list[Image.Image]:
    """Находит горизонтальные полосы с текстом и обрезает каждую отдельно.

    Пороговая маска нужна только для поиска строк. В OCR передаются исходные
    цветные фрагменты, чтобы не терять детали почерка.
    """
    серое = ImageOps.grayscale(изображение)
    яркость = np.asarray(серое, dtype=np.uint8)
    высота, ширина = яркость.shape

    # Размытие даёт оценку освещения под бумагой и помогает при лёгкой тени.
    радиус = max(8, min(35, min(ширина, высота) // 40))
    фон = np.asarray(серое.filter(ImageFilter.GaussianBlur(radius=радиус)))
    порог = порог_отделения_чернил(яркость)
    локальный_порог = np.minimum(порог, фон.astype(np.int16) - 25)
    чернила = яркость.astype(np.int16) < локальный_порог

    # Длинные линии клетчатой/линейчатой бумаги заметно плотнее букв по всей
    # ширине или высоте. Убираем такие ряды из маски, не меняя исходное фото.
    горизонтальные_линии = np.flatnonzero(чернила.sum(axis=1) > ширина * 0.65)
    вертикальные_линии = np.flatnonzero(чернила.sum(axis=0) > высота * 0.65)
    for ряд in горизонтальные_линии:
        чернила[max(0, ряд - 1):min(высота, ряд + 2), :] = False
    for колонка in вертикальные_линии:
        чернила[:, max(0, колонка - 1):min(ширина, колонка + 2)] = False

    # Отбрасываем одиночные точки, затем соединяем близкие части одной строки.
    минимум_пикселей = max(2, math.ceil(ширина * 0.00035))
    активные_ряды = чернила.sum(axis=1) >= минимум_пикселей
    допуск_между_частями = max(5, round(высота * 0.003))
    кандидаты = _сгруппировать_строки(активные_ряды, допуск_между_частями)
    минимум_высоты = max(5, round(высота * 0.002))

    строки: list[Image.Image] = []
    for верх, низ in кандидаты:
        высота_текста = низ - верх
        if высота_текста < минимум_высоты:
            continue
        вертикальное_поле = max(6, round(высота_текста * 0.18))
        y0 = max(0, верх - вертикальное_поле)
        y1 = min(высота, низ + вертикальное_поле)

        пиксели_по_колонкам = чернила[y0:y1].sum(axis=0)
        активные_колонки = np.flatnonzero(пиксели_по_колонкам > 0)
        if активные_колонки.size:
            поле_по_ширине = max(8, round((y1 - y0) * 0.18))
            x0 = max(0, int(активные_колонки[0]) - поле_по_ширине)
            x1 = min(ширина, int(активные_колонки[-1]) + 1 + поле_по_ширине)
            if x1 > x0:
                строки.append(изображение.crop((x0, y0, x1, y1)))

    if not строки:
        raise ValueError(
            "Не удалось найти строки текста. Убедитесь, что текст тёмный, "
            "страница целиком видна и фото не слишком размыто."
        )
    return строки


def распознать_фрагменты(
    фрагменты: list[Image.Image], процессор, модель, устройство: str
) -> list[str]:
    """Распознаёт список строк одной уже загруженной OCR-моделью."""
    результаты = []
    for фрагмент in фрагменты:
        вход = процессор(фрагмент, return_tensors="pt").pixel_values.to(устройство)
        with torch.no_grad():
            токены = модель.generate(
                вход,
                num_beams=4,
                no_repeat_ngram_size=0,
                max_length=128,
            )
        текст = процессор.batch_decode(токены, skip_special_tokens=True)[0].strip()
        текст = re.sub(r"\s+([,.:;!?])", r"\1", текст)
        результаты.append(текст)
    return результаты


def исправить_строки(строки: list[str], устройство: str) -> list[str]:
    """Корректирует распознанные строки, загрузив языковую модель один раз."""
    токенизатор = AutoTokenizer.from_pretrained(CORRECTOR_NAME)
    корректор = AutoModelForSeq2SeqLM.from_pretrained(CORRECTOR_NAME)
    корректор.to(устройство)
    корректор.eval()

    исправленные = []
    for текст in строки:
        if not текст.strip():
            исправленные.append(текст)
            continue
        вход = токенизатор(
            текст, return_tensors="pt", truncation=True, max_length=512
        )
        вход = {имя: значение.to(устройство) for имя, значение in вход.items()}
        with torch.no_grad():
            токены = корректор.generate(**вход, num_beams=4, max_new_tokens=128)
        исправленные.append(
            токенизатор.decode(токены[0], skip_special_tokens=True).strip()
        )
    return исправленные


def распознать(
    путь_к_изображению: str,
    исправлять: bool = True,
    использовать_адаптер: bool = True,
    целая_страница: bool = False,
) -> tuple[str, str | None]:
    """Распознаёт одну строку либо страницу, нарезанную на строки."""
    устройство = выбрать_устройство()
    изображение = ImageOps.exif_transpose(Image.open(путь_к_изображению)).convert("RGB")
    фрагменты = (
        выделить_строки_страницы(изображение)
        if целая_страница
        else [изображение]
    )
    процессор, модель = загрузить_распознаватель(использовать_адаптер, устройство)
    распознанные_строки = распознать_фрагменты(фрагменты, процессор, модель, устройство)
    исходный_текст = "\n".join(распознанные_строки)

    if not исправлять:
        return исходный_текст, None

    # Корректор не видит изображение, поэтому его версия всегда отдельная.
    исправленные_строки = исправить_строки(распознанные_строки, устройство)
    return исходный_текст, "\n".join(исправленные_строки)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Распознаёт рукописный русский текст на фото одной строки или страницы."
    )
    parser.add_argument("изображение", help="Путь к фото или скану")
    parser.add_argument(
        "--page",
        action="store_true",
        help="Найти строки на странице и распознавать их по порядку сверху вниз",
    )
    parser.add_argument(
        "--ocr-only",
        action="store_true",
        help="Не загружать вторую модель-корректор",
    )
    parser.add_argument(
        "--base-only",
        action="store_true",
        help="Игнорировать персональный адаптер и использовать исходную OCR-модель",
    )
    args = parser.parse_args()
    исходный, исправленный = распознать(
        args.изображение,
        исправлять=not args.ocr_only,
        использовать_адаптер=not args.base_only,
        целая_страница=args.page,
    )
    print(f"Распознано: {исходный}")
    if исправленный is not None:
        print(f"После проверки: {исправленный}")


if __name__ == "__main__":
    main()
