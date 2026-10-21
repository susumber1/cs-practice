"""Функции для подсчёта значений и работы с множествами."""


def count_items(values: list) -> dict:
    """Вернуть словарь с количеством появлений каждого значения."""
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def unique_sorted(values: list) -> list:
    """Вернуть уникальные значения по возрастанию."""
    return sorted(set(values))


def common(first: list, second: list) -> list:
    """Вернуть значения, присутствующие в обоих списках."""
    return sorted(set(first) & set(second))


def only_in_first(first: list, second: list) -> list:
    """Вернуть значения из первого списка, которых нет во втором."""
    return sorted(set(first) - set(second))
