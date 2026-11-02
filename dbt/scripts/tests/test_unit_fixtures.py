import csv
import unittest
from collections import Counter
from pathlib import Path

import yaml


class UnitFixtureTests(unittest.TestCase):
    def test_expected_rows_have_the_same_columns(self):
        tests = yaml.safe_load(Path("models/unit_tests.yml").read_text())["unit_tests"]
        for test in tests:
            rows = test["expect"]["rows"]
            for row in rows:
                with self.subTest(test=test["name"]):
                    self.assertEqual(list(row), list(rows[0]))

    def test_merchant_expectations_match_fixture(self):
        tests = yaml.safe_load(Path("models/unit_tests.yml").read_text())["unit_tests"]
        test = next(item for item in tests if item["name"] == "merchant_flag_thresholds")
        counts, frauds = Counter(), Counter()
        with Path("tests/fixtures/merchant_flags.csv").open(newline="") as stream:
            for row in csv.DictReader(stream):
                counts[row["merchant"]] += 1
                frauds[row["merchant"]] += int(row["is_fraud"])
        config = yaml.safe_load(Path("dbt_project.yml").read_text())["vars"]
        for row in test["expect"]["rows"]:
            name = row["merchant"]
            rate = 100.0 * frauds[name] / counts[name]
            with self.subTest(merchant=name):
                self.assertEqual(row["transactions_count"], counts[name])
                self.assertEqual(row["fraud_rate"], rate)
                self.assertEqual(row["is_suspicious"], int(
                    counts[name] >= config["merchant_min_transactions"]
                    and rate >= config["merchant_fraud_rate"]
                ))
