"""Инструменты для чтения и сводки простых CSV-таблиц."""


def read_rows(lines: list[str]) -> list[dict[str, str]]:
    """Разобрать строки CSV; первая непустая строка задаёт имена колонок."""
    rows: list[dict[str, str]] = []
    headers: list[str] | None = None

    for line in lines:
        if not line.strip():
            continue

        fields = [value.strip() for value in line.strip().split(",")]
        if headers is None:
            headers = fields
            continue

        if len(fields) != len(headers):
            continue

        rows.append(dict(zip(headers, fields)))

    return rows


def count_types(rows: list[dict[str, str]]) -> dict[str, int]:
    """Посчитать число записей для каждого типа."""
    counts: dict[str, int] = {}
    for row in rows:
        kind = row.get("тип", "")
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def total_minutes(rows: list[dict[str, str]], kind: str) -> float:
    """Сложить длительности указанного типа, пропуская некорректные значения."""
    total = 0.0
    for row in rows:
        if row.get("тип") != kind:
            continue
        value = row.get("минуты", "").replace(",", ".")
        try:
            total += float(value)
        except ValueError:
            continue
    return round(total, 1)


def to_csv(counts: dict[str, int]) -> str:
    """Вернуть CSV-сводку с типами в алфавитном порядке."""
    lines = ["тип,количество"]
    lines.extend(f"{kind},{counts[kind]}" for kind in sorted(counts))
    return "\n".join(lines) + "\n"
