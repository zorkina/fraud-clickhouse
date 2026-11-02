import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from scripts.project_state import code_hash


def main():
    result = json.loads(Path('evidence/run.json').read_text())
    reconciliation = json.loads(Path('evidence/reconciliation.json').read_text())
    screenshot = json.loads(Path('evidence/screenshot.json').read_text())
    image = Path('evidence/dbt-docs.png').read_bytes()
    if result['code_sha256'] != code_hash():
        raise RuntimeError('Файлы проекта изменились после проверки')
    if len(reconciliation) != 6 or not all(item['matches_reference'] for item in reconciliation.values()):
        raise RuntimeError('Не все витрины прошли независимую сверку')
    if len(image) < 10000 or image[:8] != b'\x89PNG\r\n\x1a\n' or not screenshot['contains_p95_column']:
        raise RuntimeError('Не получен скриншот документации')
    dag = Path('evidence/dbt-dag.png').read_bytes()
    if len(dag) < 10000 or dag[:8] != b'\x89PNG\r\n\x1a\n' or len(screenshot['graph_nodes']) < 8:
        raise RuntimeError('Не получен скриншот графа dbt Docs')
    result.update(status='passed', completed_at=datetime.now(timezone.utc).isoformat(),
                  reconciliation=reconciliation, screenshot='dbt-docs.png', dag='dbt-dag.png')
    result['evidence_sha256'] = {
        path.name:hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path('evidence').iterdir())
        if path.is_file() and path.suffix in ('.log','.json','.png') and path.name != 'check.json'
    }
    Path('evidence/check.json').write_text(json.dumps(result,indent=2)+'\n')
    versions=result['versions']; tests=result['dbt_tests']
    lines=['# Результаты запуска','',f"Источник: train.csv, {result['source']['rows']} строк, {result['source']['fraud_count']} меток фрода.",'',
           f"dbt-core {versions['dbt-core']}, dbt-clickhouse {versions['dbt-clickhouse']}.",'',
           f"Прошли {tests['data_tests_passed']} data tests и {tests['unit_tests_passed']} unit tests. SQLFluff завершился без ошибок.",'',
           'Все шесть витрин сверены с отдельным расчетом по CSV.','',
           '| Витрина | Строк |','|---|---:|']
    lines.extend(f'| {name} | {item["rows"]} |' for name,item in reconciliation.items())
    lines+=['','[Лог dbt test](dbt-test.log) · [Лог SQLFluff](sqlfluff.log) · [Скриншот документации](dbt-docs.png) · [Граф dbt](dbt-dag.png)','']
    Path('evidence/README.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f"Готово. Строк источника: {result['source']['rows']}. Витрин: 6.")
    print(f"Data tests: {tests['data_tests_passed']}. Unit tests: {tests['unit_tests_passed']}. SQLFluff: passed.")
    print('Документация: http://localhost:8084')


if __name__ == '__main__':
    main()
