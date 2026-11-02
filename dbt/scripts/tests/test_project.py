import csv
import re
import unittest
from pathlib import Path
import yaml


class ProjectTests(unittest.TestCase):
    def test_six_marts(self):
        self.assertEqual(len(list(Path('models/marts').glob('*.sql'))),6)

    def test_all_models_documented(self):
        actual={p.stem for p in Path('models').rglob('*.sql')}
        documented=set()
        for path in Path('models').rglob('*.yml'):
            for model in yaml.safe_load(path.read_text()).get('models',[]):
                self.assertTrue(model.get('description'))
                self.assertTrue(model.get('columns'))
                self.assertTrue(all(column.get('description') for column in model['columns']))
                documented.add(model['name'])
        self.assertEqual(actual,documented)

    def test_ten_native_unit_tests(self):
        tests=yaml.safe_load(Path('models/unit_tests.yml').read_text())['unit_tests']
        self.assertEqual(len(tests),10)
        self.assertEqual(len({test['name'] for test in tests}),len(tests))
        for test in tests:
            self.assertTrue(test['expect']['rows'])
            for item in test['given']:
                if 'fixture' in item:
                    self.assertTrue(Path('tests/fixtures',item['fixture']+'.csv').is_file())

    def test_seed_has_50_states_and_dc(self):
        with Path('seeds/states.csv').open() as file:
            rows=list(csv.DictReader(file))
        self.assertEqual(len(rows),51)
        self.assertEqual(sum(int(x['is_state']) for x in rows),50)
        self.assertEqual(len({x['state_code'] for x in rows}),51)

    def test_all_packages_used(self):
        text='\n'.join(p.read_text() for p in Path('models').rglob('*') if p.suffix in ('.sql','.yml'))
        for package in ('dbt_utils','dbt_date','dbt_expectations'):
            self.assertIn(package+'.',text)

    def test_sql_uses_dbt_dependencies(self):
        for path in Path('models/marts').glob('*.sql'):
            self.assertIn("ref('stg_transactions')",path.read_text())
        self.assertIn("source('raw', 'transactions')",Path('models/staging/stg_transactions.sql').read_text())

    def test_required_checks_are_not_disabled(self):
        text=Path('.sqlfluff').read_text()
        self.assertIn('dbt_skip_compilation_error = False',text)
        self.assertNotRegex(text,r'(?m)^ignore\s*=')
        self.assertNotIn('noqa','\n'.join(p.read_text() for p in Path('models').rglob('*.sql')))
