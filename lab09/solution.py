import numpy as np


def make_hours() -> list[int]:
    """Создать список часов от 0 до 21 с шагом 3."""
    return np.arange(0, 22, 3).tolist()


def vector_report(values: list[float]) -> dict:
    """Вернуть основные элементы и срезы вектора."""
    arr = np.asarray(values, dtype=float)

    return {
        "third": float(arr[2]),
        "last": float(arr[-1]),
        "middle": arr[2:6].tolist(),
        "every_second": arr[::2].tolist(),
        "reversed": arr[::-1].tolist(),
    }


def change_vector(values: list[float]) -> list[float]:
    """Изменить элементы независимой копии вектора."""
    arr = np.asarray(values, dtype=float).copy()
    arr[2:5] = 99
    arr[::2] = -1
    return arr.tolist()


def cap_above(values: list[float], limit: float) -> list[float]:
    """Заменить все значения больше limit на limit с помощью одной маски."""
    arr = np.asarray(values, dtype=float).copy()
    arr[arr > limit] = limit
    return arr.tolist()


def celsius_to_fahrenheit(values: list[float]) -> list[float]:
    """Перевести температуры из градусов Цельсия в Фаренгейты."""
    arr = np.asarray(values, dtype=float)
    fahrenheit = arr * 9 / 5 + 32
    return fahrenheit.tolist()
