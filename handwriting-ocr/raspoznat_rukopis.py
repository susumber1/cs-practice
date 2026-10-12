"""Распознавание одной строки рукописного текста на русском языке.

Модель уже обучена заранее. Этот скрипт только загружает её и делает прогноз.
При первом запуске веса модели будут скачаны из Hugging Face.
"""

import argparse
import re
from pathlib import Path

import torch
from PIL import Image, ImageOps
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


def распознать(
    путь_к_изображению: str,
    исправлять: bool = True,
    использовать_адаптер: bool = True,
) -> tuple[str, str | None]:
    """Распознаёт строку и при необходимости корректирует ошибки по контексту."""
    устройство = выбрать_устройство()

    # Процессор подготавливает изображение и превращает предсказание в текст.
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

    изображение = ImageOps.exif_transpose(Image.open(путь_к_изображению))
    вход = процессор(изображение, return_tensors="pt").pixel_values
    вход = вход.to(устройство)
    with torch.no_grad():
        токены = модель.generate(
            вход,
            num_beams=4,
            no_repeat_ngram_size=0,
            max_length=128,
        )

    исходный_текст = процессор.batch_decode(токены, skip_special_tokens=True)[0].strip()
    исходный_текст = re.sub(r"\s+([,.:;!?])", r"\1", исходный_текст)

    if not исправлять or not исходный_текст.strip():
        return исходный_текст, None

    # Вторая модель ищет вероятные орфографические и пунктуационные ошибки.
    # Она не видит изображение, поэтому её вариант всегда выводится отдельно.
    токенизатор_корректора = AutoTokenizer.from_pretrained(CORRECTOR_NAME)
    корректор = AutoModelForSeq2SeqLM.from_pretrained(CORRECTOR_NAME)
    корректор.to(устройство)
    корректор.eval()

    вход_корректора = токенизатор_корректора(
        исходный_текст, return_tensors="pt", truncation=True, max_length=512
    )
    вход_корректора = {
        имя: значение.to(устройство) for имя, значение in вход_корректора.items()
    }

    with torch.no_grad():
        исправленные_токены = корректор.generate(
            **вход_корректора,
            num_beams=4,
            max_new_tokens=128,
        )

    исправленный_текст = токенизатор_корректора.decode(
        исправленные_токены[0], skip_special_tokens=True
    )
    return исходный_текст, исправленный_текст


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Распознаёт одну строку рукописного русского текста на изображении."
    )
    parser.add_argument("изображение", help="Путь к фото или скану строки")
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
    )
    print(f"Распознано: {исходный}")
    if исправленный is not None:
        print(f"После проверки: {исправленный}")


if __name__ == "__main__":
    main()
