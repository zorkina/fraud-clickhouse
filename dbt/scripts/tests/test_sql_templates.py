import sqlite3
import unittest
from pathlib import Path

from jinja2 import Environment, StrictUndefined


class RateTemplateTests(unittest.TestCase):
    def setUp(self):
        text = Path("macros/fraud_rate.sql").read_text()
        self.macro = Environment(undefined=StrictUndefined).from_string(text).module.fraud_rate
        self.connection = sqlite3.connect(":memory:")
        self.addCleanup(self.connection.close)
        self.connection.create_function("toFloat64", 1, lambda value: None if value is None else float(value))

    def calculate(self, numerator, denominator):
        expression = self.macro(numerator, denominator)
        return self.connection.execute("select " + expression).fetchone()[0]

    def test_casts_both_operands(self):
        sql = self.macro("sumIf(amount, is_fraud = 1)", "sum(amount)")
        self.assertIn("toFloat64(sumIf(amount, is_fraud = 1))", sql)
        self.assertIn("toFloat64(sum(amount))", sql)
        self.assertNotIn("100.0 * sumIf", sql)

    def test_decimal_percentage(self):
        self.assertEqual(self.calculate("'30.00'", "'40.00'"), 75.0)

    def test_zero_turnover(self):
        self.assertEqual(self.calculate("'0.00'", "'0.00'"), 0.0)

    def test_integer_threshold(self):
        self.assertEqual(self.calculate("1", "50"), 2.0)

    def test_full_fraud(self):
        self.assertEqual(self.calculate("'9.99'", "'9.99'"), 100.0)

    def test_zero_frauds(self):
        self.assertEqual(self.calculate("0", "8"), 0.0)

    def test_sums_remain_decimal(self):
        sql = Path("models/marts/mart_fraud_by_category.sql").read_text()
        self.assertIn("sum(amount) as total_amount", sql)
        self.assertIn("sumIf(amount, is_fraud = 1) as fraud_amount", sql)
