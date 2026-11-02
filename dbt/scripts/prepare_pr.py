import argparse
import hashlib
import json
from pathlib import Path
from scripts.data import fingerprint
from scripts.project_state import code_hash


def main(repository, branch):
    path = Path('evidence/check.json')
    if not path.exists():
        raise RuntimeError('Нет итоговой проверки. Сначала требуется успешный запуск start.sh.')
    result = json.loads(path.read_text())
    if result.get('status') != 'passed' or result['code_sha256'] != code_hash():
        raise RuntimeError('Нет успешной проверки текущей версии файлов')
    if fingerprint('data/train.csv') != result['source']['sha256']:
        raise RuntimeError('Источник изменился после проверки')
    for name, expected in result['evidence_sha256'].items():
        actual = hashlib.sha256(Path('evidence',name).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f'Артефакт проверки изменился: {name}')
    counts = result['dbt_tests']; versions=result['versions']
    raw = f'https://raw.githubusercontent.com/{repository}/{branch}/dbt/evidence'
    blob = f'https://github.com/{repository}/blob/{branch}/dbt'
    lines = ['## dbt и ClickHouse','',
        f"dbt-core {versions['dbt-core']}, dbt-clickhouse {versions['dbt-clickhouse']}.",'',
        f"Источник: train.csv, {result['source']['rows']} строк. Слой raw находится в transactions_db.transactions.",'',
        '## Витрины','',
        '| Модель | Строк |','|---|---:|']
    lines.extend(f'| {name} | {info["rows"]} |' for name,info in result['reconciliation'].items())
    lines += ['', '## Проверки','',
        f"Прошли {counts['data_tests_passed']} data tests и {counts['unit_tests_passed']} нативных unit tests. SQLFluff завершился без ошибок.",'',
        'Проверены обязательные поля, уникальность ключей, допустимые значения, связи со справочником, границы метрик и сохранение количества и сумм транзакций. Все витрины сверены с отдельным расчетом по CSV.','',
        f'[Лог dbt test]({blob}/evidence/dbt-test.log) · [Результаты тестов]({blob}/evidence/dbt_test_results.json) · [Лог SQLFluff]({blob}/evidence/sqlfluff.log)','',
        '## Документация','',f'![Граф dbt Docs]({raw}/dbt-dag.png)','',
        f'![Страница витрины]({raw}/dbt-docs.png)','',
        '## Запуск','',
        '```bash','bash dbt/start.sh /полный/путь/к/teta-ml-1-2025.zip','```','',
        'В корне добавлены Makefile и .pre-commit-config.yaml. Конфигурация линтера находится в dbt/.sqlfluff. Исходный CSV в PR не включен.','']
    Path('evidence/PR_BODY.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Код, данные и артефакты соответствуют успешному запуску.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--repository',required=True)
    parser.add_argument('--branch',default='hw4-dbt')
    args=parser.parse_args()
    main(args.repository,args.branch)
