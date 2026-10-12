import argparse
import csv
import fcntl
import io
import json
import subprocess
import sys
import time
from decimal import Decimal
from itertools import zip_longest
from pathlib import Path

from app.benchmark import benchmark
from app.clickhouse import ClickHouse, read_sql
from app.csv_data import check_record, read_records, scan_source
from app.producer import send

TABLES = ("transactions_base", "transactions_optimized")


def normalize_result(text):
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != ["us_state", "cat_id", "max_amount"]:
        raise AssertionError("Неверные столбцы результата SQL")
    result = [(row["us_state"], row["cat_id"], Decimal(row["max_amount"])) for row in reader]
    if len(result) != len({row[0] for row in result}):
        raise AssertionError("В результате SQL повторяется штат")
    return result


def wait_for_rows(client, expected, timeout=600):
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        counts = {}
        for table in TABLES:
            row = client.rows(f"SELECT count() AS n, uniqExact(row_id) AS unique_n FROM fraud.{table}")[0]
            n, unique_n = int(row["n"]), int(row["unique_n"])
            if n != unique_n or n > expected:
                raise RuntimeError(f"В {table} есть повторы или лишние строки: {n}, уникальных: {unique_n}")
            counts[table] = n
        state = tuple(counts.values())
        if state != previous:
            print("ClickHouse: " + ", ".join(f"{table}={count}" for table, count in counts.items()), flush=True)
            previous = state
        if all(count == expected for count in counts.values()):
            return counts
        time.sleep(2)
    raise TimeoutError("ClickHouse не получил все сообщения за 10 минут")


def audit(client, path, table, expected_count):
    query = f"SELECT * FROM fraud.{table} ORDER BY row_id"
    count = 0
    for expected, actual in zip_longest(read_records(path), client.stream_rows(query)):
        if expected is None or actual is None:
            raise AssertionError(f"Не совпало количество строк при проверке {table}")
        check_record(expected, actual)
        count += 1
    if count != expected_count:
        raise AssertionError(f"В {table} проверено {count} строк вместо {expected_count}")
    print(f"{table}: все {count} строк сверены с CSV", flush=True)


def report(output, checks, summary, storage):
    output = Path(output)
    (output / "check.json").write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = f"""# Результат запуска

Источник: `{checks['source_file']}`, {checks['csv_rows']} строк. ClickHouse {checks['clickhouse_version']}.

Kafka подтвердила {checks['kafka_messages']} сообщений. В обеих таблицах по {checks['csv_rows']} строк без повторяющихся row_id. Все поля каждой строки сверены с CSV. Результаты SQL до и после оптимизации совпали с независимым расчетом в Python. В итоговом файле {checks['result_rows']} строк, по одной на каждое значение us_state, включая DC.

## Замеры

По 7 измерений каждого варианта после прогрева. Порядок запуска чередуется, query cache выключен, max_threads=2. Перед замером обе таблицы приведены к одной части через OPTIMIZE FINAL. Это отдельный шаг эксперимента, а не настройка фоновой загрузки.

| Вариант | Медиана на сервере, мс | Медиана с HTTP, мс | Прочитано строк | Прочитано байт |
|---|---:|---:|---:|---:|
"""
    for row in summary:
        text += f"| {row['variant']} | {row['server_ms_median']:g} | {row['client_ms_median']:g} | {row['read_rows_median']:g} | {row['read_bytes_median']:g} |\n"
    before, _, after = summary
    if after["server_ms_median"] > 0:
        ratio = before["server_ms_median"] / after["server_ms_median"]
        text += f"\nОтношение медиан времени base / optimized: {ratio:.2f}. Это результат этого запуска, не гарантия для другого компьютера.\n"
    else:
        text += "\nЧасть запросов заняла меньше миллисекунды. Отношение серверных времен не рассчитывалось из-за округления до нуля.\n"
    text += "\nИспользование проекции by_state проверено по system.query_log. Исходные измерения находятся в benchmark.csv. Время со стороны клиента включает HTTP, серверное время берется из query_duration_ms. Замер выполнен на прогретых данных, это не тест холодного диска.\n\n## Хранение\n\n| Таблица | Строк | Частей | bytes_on_disk |\n|---|---:|---:|---:|\n"
    for row in storage:
        text += f"| {row['table']} | {row['rows']} | {row['parts']} | {row['bytes_on_disk']} |\n"
    text += "\nБазовая таблица оставлена для сравнения. Поэтому весь проект хранит две копии транзакций. Проекция дополнительно занимает место и рассчитывается при вставке.\n"
    (output / "README.md").write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/test.csv")
    arguments = parser.parse_args()
    output = Path("results")
    output.mkdir(exist_ok=True)
    with (output / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Проверка уже запущена в другом процессе") from exc
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], check=True)
        path = Path(arguments.csv)
        print("Проверка исходного test.csv...", flush=True)
        source = scan_source(path)
        print(f"CSV: {source['rows']} строк, {len(source['expected'])} значений us_state", flush=True)
        client = ClickHouse()
        for filename in ("sql/01_base.sql", "sql/02_optimized.sql", "sql/03_kafka.sql"):
            client.apply_file(filename)
        kafka_messages = send(path, source)
        counts = wait_for_rows(client, source["rows"])
        for table in TABLES:
            audit(client, path, table, source["rows"])
        results = []
        for filename in ("sql/04_max_by_state_base.sql", "sql/05_max_by_state.sql"):
            text = client.execute(read_sql(filename) + " FORMAT CSVWithNames")
            if normalize_result(text) != source["expected"]:
                raise AssertionError(f"SQL {filename} не совпал с независимым расчетом")
            results.append(text)
        for filename, text in zip(("max_by_state_base.csv", "max_by_state.csv"), results):
            (output / filename).write_text(text, encoding="utf-8")
        print("SQL: обе версии совпали с независимым расчетом", flush=True)
        print("Замер запросов и размера таблиц...", flush=True)
        summary, storage = benchmark(client, output)
        checks = {
            "source_file": path.name,
            "source_sha256": source["sha256"],
            "csv_rows": source["rows"],
            "kafka_messages": kafka_messages,
            "clickhouse_rows": counts,
            "all_columns_compared": True,
            "result_rows": len(source["expected"]),
            "sql_matches_python": True,
            "projection_used": True,
            "clickhouse_version": client.execute("SELECT version()").strip(),
        }
        report(output, checks, summary, storage)
        print(f"\nГотово. CSV: {source['rows']}, Kafka: {kafka_messages}, ClickHouse: {source['rows']} в каждой таблице.", flush=True)
        print(f"Строк результата: {len(source['expected'])}. Файл: results/max_by_state.csv", flush=True)
        print("Проекция by_state использована. Замеры: results/README.md", flush=True)
        for row in summary:
            print(f"{row['variant']}: {row['server_ms_median']:g} мс, прочитано {row['read_rows_median']:g} строк", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"\nЗапуск остановлен: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)
