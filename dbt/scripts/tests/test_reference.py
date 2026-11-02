import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import yaml
from scripts.reference import build_reference, compare_rows, percentile

CONFIG = yaml.safe_load(Path('dbt_project.yml').read_text())['vars']
STATES = {'CA': 'California', 'DC': 'District of Columbia'}


def row(**values):
    result = dict(transaction_time=datetime(2020,3,2,10), merch='shop',cat_id='food_dining',
                  amount=Decimal('10'), name_1='Ann',name_2='Smith',gender='F',us_state='CA',
                  lat=30.0,lon=-100.0,merchant_lat=30.1,merchant_lon=-100.1,target=0)
    result.update(values)
    return result


class ReferenceTests(unittest.TestCase):
    def test_linear_percentile(self):
        self.assertEqual(percentile([1000,3000],0.95),29)

    def test_single_value_percentile(self):
        self.assertEqual(percentile([100],0.95),1)

    def test_empty_percentile_is_error(self):
        with self.assertRaises(ValueError):
            percentile([],0.95)

    def test_percentage_is_transaction_weighted(self):
        result=build_reference([row(),row(amount=Decimal('30'),target=1)],CONFIG,STATES)
        category=result['mart_fraud_by_category'][0]
        self.assertEqual(category['fraud_rate'],50)
        self.assertEqual(category['fraud_amount_pct'],75)

    def test_dc_is_retained(self):
        result=build_reference([row(us_state='DC')],CONFIG,STATES)
        self.assertEqual(result['mart_fraud_by_state'][0]['state_name'],'District of Columbia')

    def test_unknown_state_fails(self):
        with self.assertRaises(ValueError):
            build_reference([row(us_state='ZZ')],CONFIG,STATES)

    def test_customer_names_normalize(self):
        result=build_reference([row(),row(name_1=' ANN ',name_2='smith')],CONFIG,STATES)
        self.assertEqual(len(result['mart_customer_risk_profile']),1)
        self.assertEqual(result['mart_customer_risk_profile'][0]['transactions_count'],2)

    def test_fraud_prefix_is_not_a_label(self):
        result=build_reference([row(merch='fraud_shop')],CONFIG,STATES)
        self.assertEqual(result['mart_merchant_analytics'][0]['fraud_count'],0)

    def test_high_customer_threshold(self):
        result=build_reference([row(target=1)]+[row() for _ in range(19)],CONFIG,STATES)
        self.assertEqual(result['mart_customer_risk_profile'][0]['risk_level'],'HIGH')

    def test_small_customer_not_high(self):
        result=build_reference([row(target=1)]+[row() for _ in range(18)],CONFIG,STATES)
        self.assertEqual(result['mart_customer_risk_profile'][0]['risk_level'],'MEDIUM')

    def test_zero_fraud_baseline(self):
        result=build_reference([row()],CONFIG,STATES)
        hourly=result['mart_hourly_fraud_pattern'][0]
        self.assertEqual((hourly['risk_lift'],hourly['is_high_risk']),(0,0))

    def test_comparison_detects_wrong_metric(self):
        expected=[{'category':'food_dining','fraud_rate':50}]
        with self.assertRaises(AssertionError):
            compare_rows('mart_fraud_by_category',expected,[{'category':'food_dining','fraud_rate':0}])

    def test_comparison_detects_missing_group(self):
        with self.assertRaises(AssertionError):
            compare_rows('mart_fraud_by_state',[{'us_state':'CA'}],[])

    def test_comparison_detects_duplicate_key(self):
        with self.assertRaises(AssertionError):
            compare_rows('mart_fraud_by_state',[{'us_state':'CA'},{'us_state':'DC'}],
                         [{'us_state':'CA'},{'us_state':'CA'}])
