import csv
import json
from pathlib import Path
import yaml
from scripts.client import connect
from scripts.data import records
from scripts.reference import build_reference, compare_rows


def main():
    config = yaml.safe_load(Path('dbt_project.yml').read_text())['vars']
    with Path('seeds/states.csv').open() as file:
        states = {row['state_code']:row['state_name'] for row in csv.DictReader(file)}
    expected = build_reference(records('data/train.csv'), config, states)
    client = connect()
    summary = {}
    for name, rows in expected.items():
        actual = list(client.query(f'SELECT * FROM marts.{name}').named_results())
        compare_rows(name, rows, actual)
        summary[name] = {'rows':len(actual), 'matches_reference':True}
        print(f'{name}: {len(actual)} групп, расчет совпал')
    Path('evidence/reconciliation.json').write_text(json.dumps(summary, indent=2)+'\n')
    client.close()


if __name__ == '__main__':
    main()
