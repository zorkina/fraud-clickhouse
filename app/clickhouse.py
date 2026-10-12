import base64
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class ClickHouse:
    def __init__(self):
        self.url = os.getenv("CLICKHOUSE_URL", "http://clickhouse:8123").rstrip("/")
        user = os.getenv("CLICKHOUSE_USER", "student")
        password = os.getenv("CLICKHOUSE_PASSWORD", "fraud_local")
        self.authorization = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def request(self, query, settings=None, query_id=None, stream=False):
        params = {"max_threads": 2, "max_memory_usage": 1000000000,
                  "use_query_cache": 0, "wait_end_of_query": int(not stream)}
        params.update(settings or {})
        if query_id:
            params["query_id"] = query_id
        request = Request(
            self.url + "/?" + urlencode(params),
            data=query.encode("utf-8"),
            headers={"Authorization": self.authorization, "Content-Type": "text/plain; charset=utf-8"},
        )
        try:
            return urlopen(request, timeout=300)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ClickHouse HTTP {exc.code}: {detail}") from exc

    def execute(self, query, settings=None, query_id=None):
        with self.request(query, settings, query_id) as response:
            return response.read().decode("utf-8")

    def rows(self, query, settings=None):
        text = self.execute(query.rstrip().rstrip(";") + " FORMAT JSONEachRow", settings)
        return [json.loads(line, parse_float=Decimal) for line in text.splitlines() if line]

    def stream_rows(self, query):
        with self.request(query.rstrip().rstrip(";") + " FORMAT JSONEachRow", stream=True) as response:
            for line in response:
                if line.strip():
                    yield json.loads(line, parse_float=Decimal)

    def apply_file(self, path):
        for statement in Path(path).read_text(encoding="utf-8").split(";"):
            if statement.strip():
                self.execute(statement)


def read_sql(path):
    return Path(path).read_text(encoding="utf-8").strip().rstrip(";")
