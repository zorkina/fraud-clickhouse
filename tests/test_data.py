import csv
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from app.csv_data import COLUMNS, check_record, convert_row, read_records, scan_source
from app.producer import encode_record
from app.run import normalize_result


def sample_row(**changes):
    row = {
        "transaction_time": "2019-09-14 02:46", "merch": "shop", "cat_id": "grocery_net",
        "amount": "25.79", "name_1": "A", "name_2": "B", "gender": "M", "street": "Street",
        "one_city": "City", "us_state": "TX", "post_code": "00123", "lat": "32.1482",
        "lon": "-99.1872", "population_city": "1897", "jobs": "Engineer",
        "merchant_lat": "31.772057", "merchant_lon": "-99.103183",
    }
    row.update(changes)
    return row


def write_source(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


class DataTests(unittest.TestCase):
    def test_number_and_postcode(self):
        row = convert_row(sample_row(), 4)
        self.assertEqual(row["post_code"], "00123")
        self.assertEqual(row["population_city"], 1897)
        self.assertEqual(row["row_id"], 4)
        self.assertEqual(row["amount"], "25.79")

    def test_timestamp_seconds(self):
        row = convert_row(sample_row(transaction_time="2019-09-14 02:46:20"), 1)
        self.assertEqual(row["transaction_time"], "2019-09-14 02:46:20")

    def test_timestamp_minutes(self):
        self.assertEqual(convert_row(sample_row(), 1)["transaction_time"], "2019-09-14 02:46:00")

    def test_invalid_timestamp(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(transaction_time="2019-02-30 00:00"), 1)

    def test_empty_field(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(cat_id=""), 1)

    def test_missing_field(self):
        row = sample_row()
        del row["us_state"]
        with self.assertRaises(ValueError):
            convert_row(row, 1)

    def test_no_target(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(target="1"), 1)

    def test_nonfinite_amounts(self):
        for amount in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                convert_row(sample_row(amount=amount), 1)

    def test_negative_amount(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(amount="-0.01"), 1)

    def test_overflow_amount(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(amount="10000000000000000"), 1)

    def test_cent_precision(self):
        with self.assertRaises(ValueError):
            convert_row(sample_row(amount="0.001"), 1)
        self.assertEqual(convert_row(sample_row(amount="87.8"), 1)["amount"], "87.80")

    def test_coordinates(self):
        for column, value in (("lat", "91"), ("merchant_lat", "-91"), ("lon", "181"), ("merchant_lon", "NaN")):
            with self.subTest(column=column), self.assertRaises(ValueError):
                convert_row(sample_row(**{column: value}), 1)

    def test_population(self):
        for value in ("-1", str(2**32), "12.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_row(sample_row(population_city=value), 1)

    def test_json_roundtrip(self):
        record = convert_row(sample_row(merch='shop, "a"'), 1)
        self.assertEqual(json.loads(encode_record(record)), record)

    def test_sql_audit_numeric_types(self):
        record = convert_row(sample_row(), 1)
        actual = {**record, "amount": Decimal("25.79"), "row_id": "1", "population_city": "1897"}
        check_record(record, actual)

    def test_audit_rejects_changed_amount(self):
        record = convert_row(sample_row(), 1)
        with self.assertRaises(AssertionError):
            check_record(record, {**record, "amount": "25.80"})

    def test_audit_rejects_changed_category(self):
        record = convert_row(sample_row(), 1)
        with self.assertRaises(AssertionError):
            check_record(record, {**record, "cat_id": "other"})

    def test_audit_rejects_missing_column(self):
        record = convert_row(sample_row(), 1)
        actual = dict(record)
        del actual["jobs"]
        with self.assertRaises(AssertionError):
            check_record(record, actual)

    def test_source_max_and_tie(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            write_source(path, [
                sample_row(amount="10", cat_id="first"),
                sample_row(amount="10.00", cat_id="second"),
                sample_row(us_state="CA", amount="80", cat_id="third"),
                sample_row(us_state="CA", amount="100", cat_id="largest"),
            ])
            result = scan_source(path)
            self.assertEqual(result["rows"], 4)
            self.assertEqual(result["expected"], [("CA", "largest", Decimal("100")), ("TX", "first", Decimal("10"))])
            self.assertEqual(len(result["sha256"]), 64)
            self.assertEqual([row["row_id"] for row in read_records(path)], [1, 2, 3, 4])

    def test_empty_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            write_source(path, [])
            with self.assertRaises(ValueError):
                scan_source(path)

    def test_wrong_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            path.write_text("index,prediction\n0,0\n")
            with self.assertRaises(ValueError):
                scan_source(path)

    def test_result_csv(self):
        result = normalize_result('"us_state","cat_id","max_amount"\n"TX","shopping_net",10.20\n')
        self.assertEqual(result, [("TX", "shopping_net", Decimal("10.20"))])

    def test_result_csv_wrong_header(self):
        with self.assertRaises(AssertionError):
            normalize_result("state,category,amount\nTX,a,1\n")

    def test_result_csv_duplicate_state(self):
        with self.assertRaises(AssertionError):
            normalize_result("us_state,cat_id,max_amount\nTX,a,1\nTX,b,2\n")


if __name__ == "__main__":
    unittest.main()
