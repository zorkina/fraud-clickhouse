import csv
import hashlib
import math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

COLUMNS = (
    "transaction_time", "merch", "cat_id", "amount", "name_1", "name_2",
    "gender", "street", "one_city", "us_state", "post_code", "lat", "lon",
    "population_city", "jobs", "merchant_lat", "merchant_lon",
)
COORDINATES = ("lat", "lon", "merchant_lat", "merchant_lon")


def convert_row(row, row_id):
    if set(row) != set(COLUMNS) or any(v is None or v == "" for v in row.values()):
        raise ValueError(f"Строка {row_id}: отсутствует поле или значение")
    record = dict(row)
    try:
        timestamp = datetime.strptime(row["transaction_time"], "%Y-%m-%d %H:%M")
    except ValueError:
        timestamp = datetime.strptime(row["transaction_time"], "%Y-%m-%d %H:%M:%S")
    record["transaction_time"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    amount = Decimal(row["amount"])
    if not amount.is_finite() or amount < 0 or amount >= Decimal("1e16"):
        raise ValueError(f"Строка {row_id}: некорректная сумма")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError(f"Строка {row_id}: больше двух знаков после запятой")
    record["amount"] = format(amount, ".2f")
    population = int(row["population_city"])
    if not 0 <= population < 2**32:
        raise ValueError(f"Строка {row_id}: некорректное население")
    record["population_city"] = population
    for column in COORDINATES:
        value = float(row[column])
        bound = 90 if column.endswith("lat") else 180
        if not math.isfinite(value) or not -bound <= value <= bound:
            raise ValueError(f"Строка {row_id}: некорректные координаты")
        record[column] = value
    record["row_id"] = row_id
    return record


def read_records(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError("Нужен исходный test.csv со столбцами в порядке из Kaggle")
        for row_id, row in enumerate(reader, 1):
            try:
                yield convert_row(row, row_id)
            except (ValueError, TypeError, InvalidOperation) as exc:
                raise ValueError(f"Ошибка в строке {row_id}: {exc}") from exc


def scan_source(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    winners = {}
    count = 0
    for record in read_records(path):
        count += 1
        state = record["us_state"]
        amount = Decimal(record["amount"])
        if state not in winners or amount > winners[state][1]:
            winners[state] = (record["cat_id"], amount)
    if not count:
        raise ValueError("test.csv пуст")
    result = [(state, *winners[state]) for state in sorted(winners)]
    return {"rows": count, "sha256": digest.hexdigest(), "expected": result}


def check_record(expected, actual):
    if set(expected) != set(actual):
        raise AssertionError("Не совпал набор столбцов")
    for key, expected_value in expected.items():
        actual_value = actual[key]
        if key == "amount":
            equal = Decimal(str(actual_value)) == Decimal(expected_value)
        elif key in COORDINATES:
            equal = math.isclose(float(actual_value), expected_value, rel_tol=0, abs_tol=1e-10)
        elif key in ("row_id", "population_city"):
            equal = int(actual_value) == expected_value
        else:
            equal = actual_value == expected_value
        if not equal:
            raise AssertionError(f"Строка {expected['row_id']}: не совпало поле {key}")
