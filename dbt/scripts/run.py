import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from scripts import load_data, reconcile
from scripts.project_state import code_hash


def command(arguments, log_name):
    with Path('evidence', log_name).open('w', encoding='utf-8') as output:
        process = subprocess.Popen(arguments, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            sys.stdout.write(line)
            output.write(line)
        status = process.wait()
    if status:
        raise RuntimeError(f'Команда {arguments[0]} завершилась с кодом {status}. Лог: evidence/{log_name}')


def inspect_tests():
    results = json.loads(Path('target/run_results.json').read_text())
    manifest = json.loads(Path('target/manifest.json').read_text())
    rows = results['results']
    failed = [row['unique_id'] for row in rows if row['status'] != 'pass']
    if not rows or failed:
        raise RuntimeError(f'Не все dbt tests прошли: {failed}')
    expected_units = {key for key in manifest.get('unit_tests', {}) if key.startswith('unit_test.fraud_analytics.')}
    actual_units = {row['unique_id'] for row in rows if row['unique_id'].startswith('unit_test.')}
    if len(expected_units) < 10 or actual_units != expected_units:
        raise RuntimeError('Нативные unit tests выполнены не полностью')
    expected_data = {key for key, node in manifest['nodes'].items() if node.get('resource_type') == 'test' and node.get('config', {}).get('enabled', True)}
    actual_data = {row['unique_id'] for row in rows if row['unique_id'].startswith('test.')}
    if actual_data != expected_data:
        raise RuntimeError('Data tests выполнены не полностью')
    shutil.copyfile('target/run_results.json', 'evidence/dbt_test_results.json')
    return {'unit_tests_passed':len(actual_units), 'data_tests_passed':len(actual_data)}


def main():
    Path('evidence').mkdir(exist_ok=True)
    for name in ['check.json', 'run.json', 'dbt-docs.png', 'dbt-dag.png', 'screenshot.json', 'reconciliation.json']:
        Path('evidence', name).unlink(missing_ok=True)
    os.environ.setdefault('DBT_PROFILES_DIR', str(Path.cwd()))
    os.environ['DBT_SEND_ANONYMOUS_USAGE_STATS'] = 'false'
    command([sys.executable, '-m', 'unittest', 'discover', '-s', 'scripts/tests', '-v'], 'python-tests.log')
    load_data.load(Path('data/train.csv'))
    command(['dbt','deps'], 'dbt-deps.log')
    command(['dbt','debug'], 'dbt-debug.log')
    command(['dbt','seed','--full-refresh'], 'dbt-seed.log')
    command(['dbt','run','--full-refresh'], 'dbt-run.log')
    command(['dbt','test'], 'dbt-test.log')
    counts = inspect_tests()
    command(['sqlfluff','lint','models','tests','--config','.sqlfluff'], 'sqlfluff.log')
    reconcile.main()
    command(['dbt','docs','generate'], 'dbt-docs.log')
    for name in ('index.html','manifest.json','catalog.json'):
        if not Path('target',name).is_file():
            raise RuntimeError(f'Не создан target/{name}')
    versions = {name:importlib.metadata.version(name) for name in
                ['dbt-core','dbt-clickhouse','sqlfluff','sqlfluff-templater-dbt','clickhouse-connect']}
    Path('evidence/versions.json').write_text(json.dumps(versions,indent=2)+'\n')
    result = {'dbt_tests':counts,'sqlfluff':'passed','models':7,'marts':6,'code_sha256':code_hash(),
              'source':json.loads(Path('evidence/source.json').read_text()),'versions':versions}
    Path('evidence/run.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f"Проверки dbt: {counts['data_tests_passed']} data tests, {counts['unit_tests_passed']} unit tests.")


if __name__ == '__main__':
    main()
