import csv
import io
import json
import statistics
import time
import uuid
from pathlib import Path

from app.clickhouse import read_sql


VARIANTS = (
    ("base", "sql/04_max_by_state_base.sql", 0),
    ("optimized_without_projection", "sql/05_max_by_state.sql", 0),
    ("optimized", "sql/05_max_by_state.sql", 1),
)


def write_csv(path, columns, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    temporary = Path(str(path) + ".tmp")
    temporary.write_text(buffer.getvalue(), encoding="utf-8")
    temporary.replace(path)


def summarize(measurements):
    result = []
    for name, _, _ in VARIANTS:
        selected = [row for row in measurements if row["variant"] == name]
        result.append({
            "variant": name,
            "runs": len(selected),
            "server_ms_median": statistics.median(row["server_ms"] for row in selected),
            "client_ms_median": round(statistics.median(row["client_ms"] for row in selected), 3),
            "read_rows_median": statistics.median(row["read_rows"] for row in selected),
            "read_bytes_median": statistics.median(row["read_bytes"] for row in selected),
            "memory_usage_max": max(row["memory_usage"] for row in selected),
        })
    return result


def benchmark(client, output, rounds=7):
    for table in ("transactions_base", "transactions_optimized"):
        client.execute(f"OPTIMIZE TABLE fraud.{table} FINAL")
    settings = {"log_queries": 1, "log_queries_probability": 1, "use_query_cache": 0, "max_threads": 2}
    for _, filename, projection in VARIANTS:
        client.execute(read_sql(filename), settings={**settings, "optimize_use_projections": projection})
    prefix = "hw2_" + uuid.uuid4().hex
    calls = []
    for iteration in range(rounds):
        order = VARIANTS[iteration % 3:] + VARIANTS[:iteration % 3]
        for name, filename, projection in order:
            query_id = f"{prefix}_{iteration}_{name}"
            started = time.perf_counter()
            client.execute(read_sql(filename), settings={**settings, "optimize_use_projections": projection}, query_id=query_id)
            calls.append({"query_id": query_id, "variant": name, "iteration": iteration + 1,
                          "client_ms": round((time.perf_counter() - started) * 1000, 3)})
    ids = ",".join("'" + row["query_id"] + "'" for row in calls)
    logs = []
    for _ in range(5):
        client.execute("SYSTEM FLUSH LOGS")
        logs = client.rows(f"""
            SELECT query_id, query_duration_ms, read_rows, read_bytes, memory_usage, projections
            FROM system.query_log
            WHERE type = 'QueryFinish' AND query_id IN ({ids})
        """)
        if len(logs) == len(calls):
            break
        time.sleep(1)
    by_id = {row["query_id"]: row for row in logs}
    if len(by_id) != len(calls):
        raise RuntimeError("В system.query_log отсутствует часть измерений")
    for row in calls:
        log = by_id[row["query_id"]]
        row.update({
            "server_ms": int(log["query_duration_ms"]),
            "read_rows": int(log["read_rows"]),
            "read_bytes": int(log["read_bytes"]),
            "memory_usage": int(log["memory_usage"]),
            "projections": ";".join(log["projections"]),
        })
    projected = [row for row in calls if row["variant"] == "optimized"]
    if not all("by_state" in row["projections"] for row in projected):
        raise RuntimeError("Запрос вернул результат, но ClickHouse не использовал проекцию by_state")
    for row in calls:
        if row["variant"] != "optimized" and row["projections"]:
            raise RuntimeError("Проекция использована в контрольном запросе, замер некорректен")
    storage = client.rows("""
        SELECT table, sum(rows) AS rows, count() AS parts,
               sum(bytes_on_disk) AS bytes_on_disk,
               sum(data_compressed_bytes) AS compressed_bytes,
               sum(data_uncompressed_bytes) AS uncompressed_bytes
        FROM system.parts
        WHERE active AND database = 'fraud'
          AND table IN ('transactions_base', 'transactions_optimized')
        GROUP BY table ORDER BY table
    """)
    for row in storage:
        for key in row:
            if key != "table":
                row[key] = int(row[key])
    summary = summarize(calls)
    output = Path(output)
    write_csv(output / "benchmark.csv", list(calls[0]), calls)
    write_csv(output / "benchmark_summary.csv", list(summary[0]), summary)
    write_csv(output / "storage.csv", list(storage[0]), storage)
    plans = []
    for name, filename, projection in VARIANTS:
        plan = client.execute("EXPLAIN indexes = 1 " + read_sql(filename), settings={"optimize_use_projections": projection})
        plans.append(name + "\n" + plan)
    (output / "query_plans.txt").write_text("\n".join(plans), encoding="utf-8")
    return summary, storage
