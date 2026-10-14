"""Сводка журнала событий из файла, указанного во входной строке."""

from tablestats import count_types, read_rows, to_csv, total_minutes


def main() -> None:
    path = input().strip()
    with open(path, encoding="utf-8") as table:
        rows = read_rows(table)

    counts = count_types(rows)
    print(len(rows))
    print(len(counts))
    print(f"{total_minutes(rows, 'ошибка'):.1f}")

    with open("summary.csv", "w", encoding="utf-8") as out:
        out.write(to_csv(counts))


if __name__ == "__main__":
    main()
