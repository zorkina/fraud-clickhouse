import csv
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from scripts.data import FIELDS, records, source_stats

BASE = dict(transaction_time='2020-03-02 10:00', merch='shop', cat_id='food_dining', amount='10.25',
            name_1='Ann', name_2='Smith', gender='F', us_state='CA', lat='30', lon='-100',
            merchant_lat='30.1', merchant_lon='-100.1', target='1')


class DataTests(unittest.TestCase):
    def write(self, row=None, fields=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / 'input.csv'
        with path.open('w') as file:
            writer = csv.DictWriter(file, fieldnames=fields or FIELDS, extrasaction='ignore')
            writer.writeheader()
            if row is not False:
                writer.writerow(BASE if row is None else row)
        return path

    def invalid(self, **values):
        row = {**BASE, **values}
        with self.assertRaises(ValueError):
            list(records(self.write(row)))

    def test_parses_money_and_target(self):
        row = next(records(self.write()))
        self.assertEqual(row['amount'], Decimal('10.25'))
        self.assertEqual(row['target'], 1)
        self.assertEqual(row['row_id'], 1)
        self.assertEqual(row['transaction_time'], datetime(2020, 3, 2, 10))

    def test_source_totals(self):
        stats = source_stats(self.write())
        self.assertEqual((stats['rows'], stats['fraud_count'], stats['amount_cents']), (1, 1, 1025))
        self.assertEqual(len(stats['sha256']), 64)

    def test_requires_label(self):
        with self.assertRaisesRegex(ValueError, 'target'):
            list(records(self.write(fields=[x for x in FIELDS if x != 'target'])))

    def test_rejects_negative_money(self):
        self.invalid(amount='-1')

    def test_rejects_nan_money(self):
        self.invalid(amount='NaN')

    def test_rejects_extra_money_precision(self):
        self.invalid(amount='1.001')

    def test_rejects_wrong_target(self):
        self.invalid(target='2')

    def test_rejects_missing_target(self):
        self.invalid(target='')

    def test_rejects_infinite_coordinate(self):
        self.invalid(lat='inf')

    def test_rejects_out_of_range_longitude(self):
        self.invalid(merchant_lon='181')

    def test_rejects_invalid_date(self):
        self.invalid(transaction_time='2020-02-30 10:00')

    def test_rejects_ambiguous_timezone(self):
        self.invalid(transaction_time='2020-03-02T10:00:00+03:00')

    def test_rejects_empty_merchant(self):
        self.invalid(merch='  ')

    def test_rejects_empty_dataset(self):
        with self.assertRaises(ValueError):
            source_stats(self.write(False))

    def test_source_is_not_modified(self):
        path = self.write()
        before = path.read_bytes()
        source_stats(path)
        self.assertEqual(before, path.read_bytes())
