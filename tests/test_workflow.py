import csv
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.benchmark import benchmark
from app.clickhouse import ClickHouse, read_sql
from app.run import wait_for_rows


class FakeClickHouse:
    def __init__(self, projection=True):
        self.logs = []
        self.projection = projection
        self.statements = []

    def execute(self, query, settings=None, query_id=None):
        self.statements.append(query)
        if query_id:
            projected = bool(settings.get("optimize_use_projections")) and self.projection
            self.logs.append({"query_id": query_id, "query_duration_ms": 1 if projected else 10,
                              "read_rows": 51 if projected else 262144, "read_bytes": 2000 if projected else 8000000,
                              "memory_usage": 10000, "projections": ["fraud.transactions_optimized.by_state"] if projected else []})
        return ""

    def rows(self, query):
        if "system.query_log" in query:
            return self.logs
        if "system.parts" in query:
            return [{"table": name, "rows": 262144, "parts": 1, "bytes_on_disk": 100000,
                     "compressed_bytes": 99999, "uncompressed_bytes": 500000}
                    for name in ("transactions_base", "transactions_optimized")]
        raise AssertionError(query)


class WorkflowTests(unittest.TestCase):
    def test_benchmark(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClickHouse()
            summary, _ = benchmark(client, directory)
            self.assertEqual(len(client.logs), 21)
            self.assertEqual([row["runs"] for row in summary], [7, 7, 7])
            self.assertEqual([row["server_ms_median"] for row in summary], [10, 10, 1])
            with (Path(directory) / "benchmark.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 21)
            self.assertEqual([r["variant"] for r in rows[:6]], [
                "base", "optimized_without_projection", "optimized",
                "optimized_without_projection", "optimized", "base"])

    def test_projection_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "не использовал проекцию"):
                benchmark(FakeClickHouse(projection=False), directory)

    def test_wait_complete(self):
        class Client:
            def rows(self, query):
                return [{"n": "20", "unique_n": "20"}]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(set(wait_for_rows(Client(), 20).values()), {20})

    def test_wait_duplicate(self):
        class Client:
            def rows(self, query):
                return [{"n": "20", "unique_n": "19"}]
        with self.assertRaises(RuntimeError):
            wait_for_rows(Client(), 20)

    def test_wait_extra(self):
        class Client:
            def rows(self, query):
                return [{"n": "21", "unique_n": "21"}]
        with self.assertRaises(RuntimeError):
            wait_for_rows(Client(), 20)

    def test_ddl_order(self):
        first = Path("sql/01_base.sql").read_text()
        second = Path("sql/02_optimized.sql").read_text()
        third = Path("sql/03_kafka.sql").read_text()
        self.assertNotIn("CREATE MATERIALIZED VIEW", first)
        self.assertIn("FROM fraud.transactions_base", second)
        self.assertIn("FROM fraud.kafka_transactions", third)

    def test_queries_same_except_table(self):
        first = read_sql("sql/04_max_by_state_base.sql")
        second = read_sql("sql/05_max_by_state.sql")
        self.assertEqual(first.replace("transactions_base", "transactions_optimized"), second)

    def test_apply_sql_files(self):
        client = ClickHouse()
        with patch.object(client, "execute") as execute:
            for filename in ("sql/01_base.sql", "sql/02_optimized.sql", "sql/03_kafka.sql"):
                client.apply_file(filename)
        self.assertEqual(execute.call_count, 6)


if __name__ == "__main__":
    unittest.main()
